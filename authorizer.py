import json
import os
import http.client
import requests
import datetime

import jwt

from cryptography.hazmat.backends import default_backend
from cryptography.x509 import load_pem_x509_certificate

# Set by serverless.yml
AUTH0_CLIENT_ID = os.getenv('AUTH0_CLIENT_ID')
AUTH0_CLIENT_PUBLIC_KEY = os.getenv('AUTH0_CLIENT_PUBLIC_KEY')


def userScheduledNow(user_id, site):
    '''
    Check if a user is currently scheduled for the given site by referencing the
    site calendar.
    Args:
        user_id: the 'sub' associated with the Auth0 user
        site: sitecode (eg. 'wmd')
    Returns:
        Boolean
    '''
    url = "https://m1vw4uqnpd.execute-api.us-east-1.amazonaws.com/dev/is-user-scheduled"
    body = json.dumps({
        "site": site,
        "user_id": user_id,
        "time": datetime.datetime.utcnow().strftime('%Y-%m-%dT%H:%M:%S.%f')[:-7] + 'Z'
    })
    response = requests.post(url, body).json()
    return response



def auth(event, context):
    '''
    Return an authorization policy for the user based on their identity role.
    This does not include checks for specific time or resource permissions,
    such as scheduled time or site ownership.
    '''
    print(f"auth event: {event}")
    whole_auth_token = event.get('authorizationToken')
    if not whole_auth_token:
        raise Exception('Unauthorized')

    print('Client token: ' + whole_auth_token)
    print('Method ARN: ' + event['methodArn'])

    token_parts = whole_auth_token.split(' ')
    auth_token = token_parts[1]
    token_method = token_parts[0]

    if not (token_method.lower() == 'bearer' and auth_token):
        print("Failing due to invalid token_method or missing auth_token")
        raise Exception('Unauthorized')

    try:
        principal_id = jwt_verify(auth_token, AUTH0_CLIENT_PUBLIC_KEY)
        userInfo = getUserInfo(auth_token)
        userRoles = getUserRoles(userInfo)
        policy = generate_policy(principal_id, 'Allow', event['methodArn'], userRoles)
        print('policy (the thing being returned): ')
        print(policy)
        return policy
    except Exception as e:
        print(f'Exception encountered: {e}')
        raise Exception('Unauthorized')


def getUserInfo(auth_token):
    # Call the auth0 user management api to get user info
    headers = { 'Authorization': f"Bearer {auth_token}", }
    url = "https://photonranch.auth0.com/userinfo"
    response = requests.get(url, headers=headers)

    # The object with the user info
    user_info = json.loads(response.content)
    return user_info

def getUserRoles(userInfo):
    userRoles = userInfo['https://photonranch.org/user_metadata']['roles']
    return userRoles


def jwt_verify(auth_token, public_key):
    public_key = format_public_key(public_key)
    pub_key = convert_certificate_to_pem(public_key)
    payload = jwt.decode(auth_token, pub_key, algorithms=['RS256'], audience=AUTH0_CLIENT_ID)
    print(f"jwt payload: {payload}")
    return payload['sub']


def generate_policy(principal_id, effect, resource, userRoles):
    return {
        'principalId': principal_id,
        'policyDocument': {
            'Version': '2012-10-17',
            'Statement': [
                {
                    "Action": "execute-api:Invoke",
                    "Effect": effect,
                    "Resource": resource
                }
            ]
        },
        # Custom policy info added in 'context'
        'context': {
            'userRoles': json.dumps(userRoles)
        }
    }

def convert_certificate_to_pem(public_key):
    cert_str = public_key.encode()
    cert_obj = load_pem_x509_certificate(cert_str, default_backend())
    pub_key = cert_obj.public_key()
    return pub_key

def format_public_key(public_key):
    public_key = public_key.replace('\n', ' ').replace('\r', '')
    public_key = public_key.replace('-----BEGIN CERTIFICATE-----', '-----BEGIN CERTIFICATE-----\n')
    public_key = public_key.replace('-----END CERTIFICATE-----', '\n-----END CERTIFICATE-----')
    return public_key