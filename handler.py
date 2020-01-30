import json, os, boto3, decimal, sys, ulid
from boto3.dynamodb.conditions import Key, Attr
from botocore.exceptions import ClientError

from helpers import *

dynamodb = boto3.resource('dynamodb')


#=========================================#
#=======       API Endpoints      ========#
#=========================================#

def newJob(event, context):
    ''' Example request body:
    {"site": "wmd", "device":"camera","instance":"camera1","action":"stop","required_params":{},"optional_params":{}}
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
    required_keys = ['site', 'device', 'instance', 'action', 'optional_params', 'required_params']
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

    dynamodb_entry = {
        "site": f"{params['site']}",        # PK, GSI1 pk
        "ulid": job_id,                     # SK
        "statusId": f"UNREAD#{job_id}",     # GSI1 sk
        "timestamp_ms": timestamp_ms,
        "deviceType": f"{params['device']}",
        "deviceInstance": f"{params['instance']}",
        "action": f"{params['action']}",
        "optional_params": params['optional_params'],
        "required_params": params['required_params'],
    }

    table_response = table.put_item(Item=dynamodb_entry)
    return create_200_response(json.dumps(table_response, indent=4, cls=DecimalEncoder))


def updateJobStatus(event, contextsite):
    ''' Example request body: 
    { "newStatus": "ACTIVE", "site": "wmd", "ulid": "01DZVYANEHR30TTKPK4XZD6MSB"}
    '''
    params = json.loads(event.get("body", ""))
    table = dynamodb.Table(os.environ['DYNAMODB_JOBS'])

    print('params:',params) # for debugging

    # TODO: add a check to see if the status update is a valid state change.

    response = table.update_item(
        Key={
            'site': params['site'],
            'ulid': params['ulid'],
        },
        UpdateExpression="set statusId = :s",
        ExpressionAttributeValues={
            ':s': f"{params['newStatus']}#{params['ulid']}"
        }
    )
    print('update status response: ',response)
    return create_200_response(json.dumps(response, indent=4, cls=DecimalEncoder))

def getUnreadJobs(event, context):
    ''' Example request body: 
    {"site": "wmd"}
    '''
    params = json.loads(event.get("body", ""))
    table = dynamodb.Table(os.environ['DYNAMODB_JOBS'])

    print('params:',params) # for debugging

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


