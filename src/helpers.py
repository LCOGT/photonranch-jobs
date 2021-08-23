import json 
import os 
import decimal 
import sys
import datetime
import requests
import boto3


#=========================================#
#=======     Helper Functions     ========#
#=========================================#

def get_response(status_code, body):
    if not isinstance(body, str):
        body = json.dumps(body)
    return {
        "statusCode": status_code, 
        "headers": {
            # Required for CORS support to work
            "Access-Control-Allow-Origin": "*",
            # Required for cookies, authorization headers with HTTPS
            "Access-Control-Allow-Credentials": "true",
        },
        "body": body
    }

# Helper class to convert a DynamoDB item to JSON.
class DecimalEncoder(json.JSONEncoder):
    def default(self, o):
        if isinstance(o, decimal.Decimal):
            if o % 1 != 0:
                return float(o)
            else:
                return int(o)
        return super(DecimalEncoder, self).default(o)


#=========================================#
#=======    External API Calls    ========#
#=========================================#

def get_current_reservations(site):
    """ Call the calendar api to get any current reservations """

    # Current time in ISO 8601 format
    iso_datestring = datetime.datetime.utcnow() \
            .strftime('%Y-%m-%dT%H:%M:%S.%f')[:-7] + 'Z'
            
    url = "https://calendar.photonranch.org/dev/get-event-at-time"
    body = json.dumps({
        "site": site,
        "time": iso_datestring,
    })
    active_reservations = requests.post(url, body).json()
    return active_reservations


#=========================================#
#======= Datastreamer Connection  ========#
#=========================================#

def get_queue_url(queueName):
    sqs_client = boto3.client("sqs", region_name="us-east-1")
    response = sqs_client.get_queue_url(
        QueueName=queueName,
    )
    return response["QueueUrl"]

def send_to_datastream(site, data):
    sqs = boto3.client('sqs')
    queue_url = get_queue_url('datastreamIncomingQueue-dev')

    payload = {
        "topic": "jobs",
        "site": site,
        "data": data,
    }
    response = sqs.send_message(
        QueueUrl=queue_url,
        MessageBody=json.dumps(payload, cls=DecimalEncoder),
    )
    return response