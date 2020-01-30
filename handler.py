import json
import os
import boto3
import decimal
import sys
import ulid
from boto3.dynamodb.conditions import Key, Attr
from botocore.exceptions import ClientError


dynamodb = boto3.resource('dynamodb')


#=========================================#
#=======     Helper Functions     ========#
#=========================================#

def create_200_response(message):
    return { 
        'statusCode': 200,
        'headers': {
            # Required for CORS support to work
            'Access-Control-Allow-Origin': '*',
            # Required for cookies, authorization headers with HTTPS
            'Access-Control-Allow-Credentials': 'true',
        },
        'body': message
    }

def create_403_response(message):
    return { 
        'statusCode': 403,
        'headers': {
            # Required for CORS support to work
            'Access-Control-Allow-Origin': '*',
            # Required for cookies, authorization headers with HTTPS
            'Access-Control-Allow-Credentials': 'true',
        },
        'body': message
    }

# Helper class to convert a DynamoDB item to JSON.
class DecimalEncoder(json.JSONEncoder):
    def default(self, o):
        if isinstance(o, decimal.Decimal):
            if o % 1 > 0:
                return float(o)
            else:
                return int(o)
        return super(DecimalEncoder, self).default(o)


### Helper Function
#def modifyItemKey(oldPk, oldSk, newPk, newSk):
    #table = dynamodb.Table(os.environ['DYNAMODB_JOBS'])

    #oldItemKey = {
        #'site': oldPk,
        #'sk': oldSk
    #}
    #oldItem = table.get_item(Key=oldItemKey)
    #newItem = oldItem['Item']
    #newItem['sk'] = newSk
    #newItem['site'] = newPk
    #put_response = table.put_item(Item=newItem)
    #delete_response = table.delete_item(Key=oldItemKey)
    #print('new item response: ',put_response)
    #print('delete old version response: ',delete_response)
def modifyItemKey(oldPk, oldSk, newItem):
    table = dynamodb.Table(os.environ['DYNAMODB_JOBS'])
    delete_response = table.delete_item(Key={'site': oldPk, 'ulid': oldSk})
    put_response = table.put_item(Item=newItem)
    print('new item response: ',put_response)
    print('delete old version response: ',delete_response)
        

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


##def reportJobStarted(event, context):
#    #params = json.loads(event.get("body", ""))
#    #table = dynamodb.Table(os.environ['DYNAMODB_JOBS'])
#
#    #site = params['site']
#    #ulid_id = f"RECEIVED#{params['timestamp']}"
#    #updatedItem = table.get_item(Key={'site':site,'ulid':ulid})['Item']
#    #updatedItem['ulid'] = ulid.replace("RECEIVED","STARTED")
#    #modifyItemKey(site, sk, updatedItem)
#    #return create_200_response('job has been marked as STARTED')
#
#def reportJobSucceeded(event, context):
#    params = json.loads(event.get("body", ""))
#    table = dynamodb.Table(os.environ['DYNAMODB_JOBS'])
#
#    site = params['site']
#    sk = f"STARTED#{params['timestamp']}"
#    updatedItem = table.get_item(Key={'site':site,'sk':sk})['Item']
#    updatedItem['sk'] = sk.replace("STARTED","SUCCEEDED")
#    modifyItemKey(site, sk, updatedItem)
#    return create_200_response('job has been marked as SUCCEEDED')
#
#def reportJobFAILED(event, context):
#    params = json.loads(event.get("body", ""))
#    table = dynamodb.Table(os.environ['DYNAMODB_JOBS'])
#
#    site = params['site']
#    sk = f"STARTED#{params['timestamp']}"
#    updatedItem = table.get_item(Key={'site':site,'sk':sk})['Item']
#    updatedItem['sk'] = sk.replace("STARTED","FAILED")
#    modifyItemKey(site, sk, updatedItem)
#    return create_200_response('job has been marked as FAILED')
#
#def reportJobCancelled(event, context):
#    params = json.loads(event.get("body", ""))
#    table = dynamodb.Table(os.environ['DYNAMODB_JOBS'])
#
#    site = params['site']
#    sk = f"STARTED#{params['timestamp']}"
#    updatedItem = table.get_item(Key={'site':site,'sk':sk})['Item']
#    updatedItem['sk'] = sk.replace("STARTED","CANCELLED")
#    modifyItemKey(site, sk, updatedItem)
#    return create_200_response('job has been marked as CANCELLED')

#def reportJobStatus(event,context):
    #params = json.loads(event.get("body", ""))
    #table = dynamodb.Table(os.environ['DYNAMODB_JOBS'])

    #newStatus = params['status']

    #site = params['site']
    #sk = f"{}"


