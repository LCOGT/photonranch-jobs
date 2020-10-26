import json, os, boto3, decimal, sys, ulid, logging, time
from boto3.dynamodb.conditions import Key, Attr
from botocore.exceptions import ClientError

from helpers import *
from authorizer import userScheduledNow

"""
TODO:

1. This code needs a lot of cleanup. 

    - specifically: document and adhere to data format conventions.
        eg. Inputs and Outputs for the api and ws endpoints.

    - refactor functions into logical files

2. Async send to all websocket clients. 

"""


logger = logging.getLogger("handler_logger")
logger.setLevel(logging.DEBUG)
dynamodb = boto3.resource('dynamodb')

def _get_response(status_code, body):
    if not isinstance(body, str):
        body = json.dumps(body)
    return {"statusCode": status_code, "body": body}

def connection_manager(event, context):
    """
    Handles connecting and disconnecting for the Websocket
    """
    jobsConnectionTable = os.getenv('JOBS_CONNECTION_TABLE')
    connectionID = event["requestContext"].get("connectionId")

    if event["requestContext"]["eventType"] == "CONNECT":
        logger.info("Connect requested")

        # Add connectionID to the database
        table = dynamodb.Table(jobsConnectionTable)
        table.put_item(Item={"ConnectionID": connectionID})
        return _get_response(200, "Connect successful.")

    elif event["requestContext"]["eventType"] in ("DISCONNECT", "CLOSE"):
        logger.info("Disconnect requested")
        
        # Remove the connectionID from the database
        table = dynamodb.Table(jobsConnectionTable)
        table.delete_item(Key={"ConnectionID": connectionID}) 
        return _get_response(200, "Disconnect successful.")

    else:
        logger.error("Connection manager received unrecognized eventType '{}'")
        return _get_response(500, "Unrecognized eventType.")

def _send_to_connection(connection_id, data, wss_url):
    gatewayapi = boto3.client("apigatewaymanagementapi", endpoint_url=wss_url)
    #data['deviceType']="filter"
    dataToSend = json.dumps(data, cls=DecimalEncoder).encode('utf-8')
    print(f"dataToSend:")
    print(json.loads(dataToSend))
    try:
        posted = gatewayapi.post_to_connection(
            ConnectionId=connection_id,
            Data=dataToSend
        )
        return posted
    except Exception as e:
        print(f"Could not send to connection {connection_id}")
        print(e)

def _send_to_all_connections(data):

    # Get all current connections
    jobsConnectionTable = os.getenv('JOBS_CONNECTION_TABLE')
    table = dynamodb.Table(jobsConnectionTable)
    response = table.scan(ProjectionExpression="ConnectionID")
    items = response.get("Items", [])
    connections = [x["ConnectionID"] for x in items if "ConnectionID" in x]

    # Send the message data to all connections
    logger.debug("Broadcasting message: {}".format(data))
    #dataToSend = {"messages": [data]}
    for connectionID in connections:
        _send_to_connection(connectionID, data, os.getenv('WSS_URL'))


def streamHandler(event, context):
    table = dynamodb.Table(os.environ['DYNAMODB_JOBS'])
    print(json.dumps(event))
    #data = event['Records'][0]['dynamodb']['NewImage']
    records = event.get('Records', [])

    for item in records:
        pk = item['dynamodb']['Keys']['site']['S']
        sk = item['dynamodb']['Keys']['ulid']['S']
    
        print(pk)
        print(sk)
        response = table.get_item(
            Key={
                "site": pk,
                "ulid": sk
            }
        )

        # If the response object doesn't have the key 'Item', there is nothing
        # to return, so close the function.
        # Note: using context.succeed() prevents the dynamodb stream from 
        # continuously retrying a bad event (eg. an event that doesn't exist)
        if response.get('Item', 'not here') == 'not here': context.succeed()

        print(json.dumps(response, indent=2, cls=DecimalEncoder))
        #_send_to_all_connections(data)
        _send_to_all_connections(response.get('Item', []))

    return _get_response(200, "stream has activated this function")

#=========================================#
#=======       API Endpoints      ========#
#=========================================#

def newJob(event, context):
    ''' Example request body:
    {
        "site": "wmd", 
        "device":"camera",
        "instance":"camera1",
        "action":"stop",
        "user_name": "some-username",
        "user_id": "userid--123124235029350",
        "required_params":{},
        "optional_params":{}
    }
    '''
    params = json.loads(event.get("body", ""))
    table = dynamodb.Table(os.environ['DYNAMODB_JOBS'])

    print("params:",params) # for debugging

    # unique, lexicographically sortable ID based on server timestamp
    # see: https://github.com/ulid/spec
    ulid_obj = ulid.new()
    job_id = ulid_obj.str
    timestamp_ms = ulid_obj.timestamp().int

    # Check that all required keys are present.
    required_keys = ['site', 'device', 'instance', 'action', 'user_name', 'user_id', 'optional_params', 'required_params']
    actual_keys = params.keys()
    for key in required_keys:
        if key not in actual_keys:
            print(f"Error: missing requied key {key}")
            return {
                "statusCode": 400,
                "body": f"Error: missing required key {key}",
                "headers": {
                    "Access-Control-Allow-Origin": "*",
                    "Access-Control-Allow-Credentials": "true",
                },
            }

    print("params:",params) # for debugging
    print(f"user scheduled now site: {params['site']}")
    print(f"user scheduled now user_id: {params['user_id']}")
    print(f"user scheduled now result: {userScheduledNow(params['user_id'], params['site'])}")
    if userScheduledNow(params['user_id'], params['site']):
        print("Disabling commands because user has an event scheduled.")
        return create_401_response("You have a calendar event scheduled now, which disables commands.")

    dynamodb_entry = {
        "site": f"{params['site']}",        # PK, GSI1 pk
        "ulid": job_id,                     # SK
        "statusId": f"UNREAD#{job_id}",     # GSI1 sk
        "user_name": params['user_name'],
        "user_id": params['user_id'],
        "timestamp_ms": timestamp_ms,
        "deviceType": f"{params['device']}",
        "deviceInstance": f"{params['instance']}",
        "action": f"{params['action']}",
        "optional_params": params['optional_params'],
        "required_params": params['required_params'],
    }

    table_response = table.put_item(Item=dynamodb_entry)

    # return the dynamodb entry and the response from the table entry. 
    return_obj = {
        **dynamodb_entry,
        "table_response": table_response,
    }
    return create_200_response(json.dumps(return_obj, indent=4, cls=DecimalEncoder))

def updateJobStatus(event, context):
    ''' Example request body: 
    { 
        "newStatus": "ACTIVE", 
        "site": "wmd", 
        "ulid": "01DZVYANEHR30TTKPK4XZD6MSB"
        "secondsUntilComplete": 15,
    }
    '''
    params = json.loads(event.get("body", ""))
    table = dynamodb.Table(os.environ['DYNAMODB_JOBS'])

    print('params:',params) # for debugging

    # TODO: add a check to see if the status update is a valid state change.

    # Time estimate for task that is starting. Empty value gets default of -1.
    secondsUntilComplete = params.get('secondsUntilComplete', -1)

    response = table.update_item(
        Key={
            'site': params['site'],
            'ulid': params['ulid'],
        },
        UpdateExpression="set statusId = :sid, secondsUntilComplete = :suc",
        ExpressionAttributeValues={
            ':sid': f"{params['newStatus']}#{params['ulid']}",
            ':suc': secondsUntilComplete
        }
    )
    print('update status response: ',response)
    return create_200_response(json.dumps(response, indent=4, cls=DecimalEncoder))

def getNewJobs(event, context):
    ''' Example request body: 
    {
        "site": "wmd"
    }
    '''
    params = json.loads(event.get("body", ""))
    table = dynamodb.Table(os.environ['DYNAMODB_JOBS'])

    print('params: ',params) # for debugging

    site = params['site']

    # Query for unread items    
    table_response = table.query(
        IndexName="StatusId",
        KeyConditionExpression=Key('site').eq(site) 
            & Key('statusId').begins_with("UNREAD")
    )

    # Update the status to 'RECEIVED' for all items returned.
    for job in table_response['Items']:
        table.update_item(
            Key={
                'site': job['site'], 
                'ulid': job['ulid'] 
            },
            UpdateExpression="set statusId = :s",
            ExpressionAttributeValues={
                ':s': f"RECEIVED#{job['ulid']}"
            }
        )

    return create_200_response(json.dumps(table_response['Items'], indent=4, cls=DecimalEncoder))

def getRecentJobs(event, context):
    ''' Example body:
    { 
        "site": "wmd, 
        "timeRange": "<number of milliseconds>", 
    }
    '''
    params = json.loads(event.get("body", ""))
    table = dynamodb.Table(os.environ['DYNAMODB_JOBS'])
    site = params['site']

    aDay = 24*3600*1000 # ms in a day (default value)
    timeRange = params.get('timeRange', aDay) / 1000 # convert to seconds

    now = time.time() #s timestamp
    earliest = now-timeRange
    earliestUlid = ulid.from_timestamp(earliest)

    table_response = table.query(
        KeyConditionExpression=Key('site').eq(site)
            & Key('ulid').gte(earliestUlid.str)
    )
    return create_200_response(json.dumps(table_response['Items'], indent=4, cls=DecimalEncoder))

def startJob(event, context):
    ''' Example body:
    { 
        "site": "wmd, 
        "ulid": "01DZVXKEV8YKCFJBM5HV0YA0WE", 
        "secondsUntilComplete": "60"
    }
    '''

    params = json.loads(event.get("body", ""))
    table = dynamodb.Table(os.environ['DYNAMODB_JOBS'])

    print('params:',params) # for debugging

    try:
        site = params['site']
        jobId = params['ulid']
    except Exception as e:
        return create_400_response("Requires 'site' and 'jobId' in the body payload.")

    # Time estimate for task that is starting. Empty value gets default of -1.
    secondsUntilComplete = params.get('secondsUntilComplete', -1)

    response = table.update_item(
        Key={
            'site': site,
            'ulid': jobId,
        },
        UpdateExpression="set statusId = :statId, secondsUntilComplete = :eta ",
        ExpressionAttributeValues={
            ':statId': f"STARTED#{jobId}",
            ':eta': secondsUntilComplete
        }
    )

    return create_200_response(json.dumps(response, indent=4, cls=DecimalEncoder))


if __name__=="__main__":
    os.environ['DYNAMODB_JOBS'] = 'photonranch-jobs1'
    os.environ['JOBS_CONNECTION_TABLE'] = 'photonranch-jobs-connections1'
    os.environ['WSS_URL'] = 'https://1tlv47sxw4.execute-api.us-east-1.amazonaws.com/dev'

    streamHandlerEvent = {
        "Records": [
            {
                "eventID": "8fa90daf0b22a7cb2d6f0b41b6b15c8a",
                "eventName": "INSERT",
                "eventVersion": "1.1",
                "eventSource": "aws:dynamodb",
                "awsRegion": "us-east-1",
                "dynamodb": {
                    "ApproximateCreationDateTime": 1581091425,
                    "Keys": {
                        "site": {
                            "S": "wmd"
                        },
                        "ulid": {
                            "S": "01E0GEY4GZNYRP3JYGSAXZ13CY"
                        }
                    },
                    "NewImage": {
                        "deviceInstance": {
                            "S": "camera1"
                        },
                        "deviceType": {
                            "S": "camera"
                        },
                        "optional_params": {
                            "M": {}
                        },
                        "site": {
                            "S": "wmd"
                        },
                        "statusId": {
                            "S": "UNREAD#01E0GEY4GZNYRP3JYGSAXZ13CY"
                        },
                        "ulid": {
                            "S": "01E0GEY4GZNYRP3JYGSAXZ13CY"
                        },
                        "required_params": {
                            "M": {}
                        },
                        "action": {
                            "S": "stop"
                        },
                        "timestamp_ms": {
                            "N": "1581091424628"
                        }
                    },
                    "SequenceNumber": "34094600000000017645425689",
                    "SizeBytes": 218,
                    "StreamViewType": "NEW_AND_OLD_IMAGES"
                },
                "eventSourceARN": "arn:aws:dynamodb:us-east-1:306389350997:table/photonranch-jobs1/stream/2020-02-06T18:04:45.173"
            }
        ]
    }

    event2 = {
    "Records": [
        {
            "eventID": "3a7c9a00d2eaa77d48365d1f9f540df8",
            "eventName": "REMOVE",
            "eventVersion": "1.1",
            "eventSource": "aws:dynamodb",
            "awsRegion": "us-east-1",
            "dynamodb": {
                "ApproximateCreationDateTime": 1581100464,
                "Keys": {
                    "site": {
                        "S": "wmd"
                    },
                    "ulid": {
                        "S": "01DZVXKEV8YKCFJBM5HV0YA0WE"
                    }
                },
                "OldImage": {
                    "deviceInstance": {
                        "S": "camera1"
                    },
                    "deviceType": {
                        "S": "camera"
                    },
                    "optional_params": {
                        "M": {}
                    },
                    "site": {
                        "S": "wmd"
                    },
                    "statusId": {
                        "S": "RECEIVED#01DZVXKEV8YKCFJBM5HV0YA0WE"
                    },
                    "ulid": {
                        "S": "01DZVXKEV8YKCFJBM5HV0YA0WE"
                    },
                    "required_params": {
                        "M": {}
                    },
                    "action": {
                        "S": "stop"
                    },
                    "timestamp_ms": {
                        "N": "1580411239272"
                    }
                },
                "SequenceNumber": "34828400000000015096291766",
                "SizeBytes": 220,
                "StreamViewType": "NEW_AND_OLD_IMAGES"
            },
            "eventSourceARN": "arn:aws:dynamodb:us-east-1:306389350997:table/photonranch-jobs1/stream/2020-02-06T18:04:45.173"
        }
    ]
}
    aJob = {"site": "wmd", "device":"camera","instance":"camera1","action":"stop","required_params":{},"optional_params":{}}


    #streamHandler(streamHandlerEvent, {})
    #streamHandler(event2, {})
    new