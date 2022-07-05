import json, os, boto3, decimal, sys, ulid, logging, time
from boto3.dynamodb.conditions import Key, Attr
from botocore.exceptions import ClientError
from http import HTTPStatus

from src.helpers import *
from src.authorizer import calendar_blocks_user_commands

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


def streamHandler(event, context):
    """Handles the job request data stream."""

    table = dynamodb.Table(os.environ['DYNAMODB_JOBS'])
    print(json.dumps(event))
    records = event.get('Records', [])

    for item in records:
        site = item['dynamodb']['Keys']['site']['S']
        sk = item['dynamodb']['Keys']['ulid']['S']
    
        response = table.get_item(
            Key={
                "site": site,
                "ulid": sk
            }
        )

        # If the response object doesn't have the key 'Item', there is nothing
        # to return, so close the function.
        # Note: using context.succeed() prevents the dynamodb stream from 
        # continuously retrying a bad event (eg. an event that doesn't exist).
        if response.get('Item', 'not here') == 'not here': context.succeed()

        print(json.dumps(response, indent=2, cls=DecimalEncoder))
        send_to_datastream(site, response.get('Item', []))

    return get_response(HTTPStatus.OK, "stream has activated this function")


#=========================================#
#=======       API Endpoints      ========#
#=========================================#

def newJob(event, context):
    """Requests a new job for an observatory and adds it to the jobs table.
    
    Requests a new job for an observatory to complete, typically from the UI,
    and adds the job to DynamoDB table for the observatory to complete.

    Args:
        JSON request body including:
            site (str): Sitecode of job (e.g. "saf").
            user_name (str): User requesting job (e.g. "Tim Beccue").
            user_id (str):
                Auth0 id of user (e.g. "google-oauth2|112301903840371673242").
            user_roles (list): List of user's auth0 roles (e.g. ['admin']).
            device (str): Device type (e.g. "camera").
            instance (str): Specific device (e.g. "camera1").
            action (str): Action to be completed (e.g. "stop").
            optional_params (dict):
                Optional parameters for the instrument
                (e.g. {bin: 1, count: 3, filter: 'R'}).
            required_params (dict): 
                Required parameters for the instrument
                (e.g. {time: 60, image_type: 'light'}).
    
    Returns:
        JSON body of table entry including:
            site (str): Same as above.
            ulid (str): Unique ID of job based on timestamp (e.g. "01G...").
            statusId (str): 
                ulid prefaced by the status of the job (e.g. "UNREAD#01G...").
            user_name (str): Same as above.
            user_id (str): Same as above.
            user_roles (list): Same as above if 'user_roles' in params, else [].
            timestamp_ms (int): Timestamp of job in ms.
            deviceType (str): Same as "device" above.
            deviceInstance (str): Same as "instance" above.
            action (str): Same as above.
            optional_params (dict): Same as above.
            required_params (dict): Same as above.
    """

    params = json.loads(event.get("body", ""))
    table = dynamodb.Table(os.environ['DYNAMODB_JOBS'])

    print("params:", params)  # for debugging

    # Unique, lexicographically sortable ID based on server timestamp.
    # See: https://github.com/ulid/spec
    ulid_obj = ulid.new()
    job_id = ulid_obj.str
    timestamp_ms = ulid_obj.timestamp().int

    # Check that all required keys are present.
    # TODO: validation with something like cerberus
    required_keys = ['site', 'device', 'instance', 'action', 'user_name', 
                     'user_id', 'optional_params', 'required_params']
    actual_keys = params.keys()
    for key in required_keys:
        if key not in actual_keys:
            print(f"Error: missing required key {key}")
            error = f"Error: missing required key {key}"
            return get_response(HTTPStatus.BAD_REQUEST, error)

    # Stop commands that are requested during someone else's reservation.
    user_id = params['user_id']
    site = params['site']
    if calendar_blocks_user_commands(user_id, site):
        print("Disabling commands because another user has a reservation now.")
        error = ("Someone else has a reservation right now. "
                 "Please see the calendar for details.")
        return get_response(HTTPStatus.UNAUTHORIZED, error)

    # Build the jobs description and send it to dynamodb
    dynamodb_entry = {
        "site": f"{params['site']}",        # PK, GSI1 pk
        "ulid": job_id,                     # SK
        "statusId": f"UNREAD#{job_id}",     # GSI1 sk
        "user_name": params['user_name'],
        "user_id": params['user_id'],
        "user_roles": params['user_roles'] if 'user_roles' in params else [],
        "timestamp_ms": timestamp_ms,
        "deviceType": f"{params['device']}",
        "deviceInstance": f"{params['instance']}",
        "action": f"{params['action']}",
        "optional_params": params['optional_params'],
        "required_params": params['required_params'],
    }
    table_response = table.put_item(Item=dynamodb_entry)

    # Return the dynamodb entry and the response from the table entry. 
    return_obj = {
        **dynamodb_entry,
        "table_response": table_response,
    }
    return get_response(HTTPStatus.OK, json.dumps(return_obj, indent=4, cls=DecimalEncoder))


def updateJobStatus(event, context):
    """Updates the status of a job.
    
    Args:
        JSON request body including:
            newStatus (str): New job status (e.g. "COMPLETED", "RECEIVED").
            site (str): Sitecode of job (e.g. "saf").
            ulid (str): Unique ID of job (e.g. "01DZVYANEHR30TTKPK4XZD6MSB").
            secondsUntilComplete (int):
                Estimate of the remaining time until a future status.
                Update of "complete" is sent, with -1 as default (e.g. 15).
    
    Returns:
        OK status code with JSON body as formatted above with updated
        job status, ulid, and secondsUntilComplete.
        Otherwise, bad request status code if missing site and jobId.
    """
    
    params = json.loads(event.get("body", ""))
    table = dynamodb.Table(os.environ['DYNAMODB_JOBS'])

    print('params:', params)  # for debugging

    # TODO: add a check to see if the status update is a valid state change.

    # Time estimate for task that is starting. Empty value gets default of -1.
    secondsUntilComplete = params.get('secondsUntilComplete', -1)

    try:
        site = params['site']
        jobId = params['ulid']
    except Exception as e:
        return get_response(HTTPStatus.BAD_REQUEST, "Requires 'site' and 'jobId' in the body payload.")

    response = table.update_item(
        Key={
            'site': site,
            'ulid': jobId,
        },
        UpdateExpression="set statusId = :statId, secondsUntilComplete = :eta ",
        ExpressionAttributeValues={
            ':statId': f"{params['newStatus']}#{params['ulid']}",
            ':eta': secondsUntilComplete
        }
    )
    print('update status response: ', response)
    return get_response(HTTPStatus.OK, json.dumps(response, indent=4, cls=DecimalEncoder))


def getNewJobs(event, context):
    """Gets list of jobs with 'UNREAD' status, changes status to 'RECEIVED'.
    
    Intended for use with the observatory code.
    
    Args:
        JSON request body including:
            site (str): site to retrieve job list from (e.g. "saf").

    Returns:
        List of updated job objects (JSON).
    """

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

    return get_response(HTTPStatus.OK, json.dumps(table_response['Items'], indent=4, cls=DecimalEncoder))


def getRecentJobs(event, context):
    """Returns list of jobs that are no older than the provided length of time.

    Args:
        JSON request body including:
            site (str): Site to retrieve job list from (e.g. "saf").
            timeRange (int): Maximum age of jobs returned in milliseconds.

    Returns:
        List of job objects (JSON) younger than maximum age.
    """

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
    return get_response(HTTPStatus.OK, json.dumps(table_response['Items'], indent=4, cls=DecimalEncoder))


def startJob(event, context):
    """Begins a job request from the jobs DnyamoDB table.

    Args:
        site (str): Site to perform job at (e.g. "saf").
        jobId (str): Unique id of the job to be performed.

    Returns:
        OK status code with updated job request table if successful.
        Bad request status code if missing site and jobId in request payload. 

    Example request body:
    { 
        "site": "saf", 
        "ulid": "01DZVXKEV8YKCFJBM5HV0YA0WE", 
        "secondsUntilComplete": "60"
    }
    """

    params = json.loads(event.get("body", ""))
    table = dynamodb.Table(os.environ['DYNAMODB_JOBS'])

    print('params:', params)  # for debugging

    try:
        site = params['site']
        jobId = params['ulid']
    except Exception as e:
        return get_response(HTTPStatus.BAD_REQUEST, "Requires 'site' and 'jobId' in the body payload.")

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

    return get_response(HTTPStatus.OK, json.dumps(response, indent=4, cls=DecimalEncoder))

