import json, os, boto3, decimal, sys, ulid
from boto3.dynamodb.conditions import Key, Attr
from botocore.exceptions import ClientError


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

def create_400_response(message):
    return { 
        'statusCode': 400,
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