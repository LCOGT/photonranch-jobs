# Photon Ranch Jobs

This repository manages job requests between the web UI and the observatory site software.

## Description

(insert description here)

## Architecture

An architecture diagram, when created, will go here.

## Dependencies

Dependencies will be listed here.

## Local Development

Clone the repository to your local machine:

```
git clone https://github.com/LCOGT/photonranch-jobs.git
cd photonranch-jobs
```

### Requirements

You will need the [Serverless Framework](https://www.serverless.com/framework/docs/getting-started) 
installed locally for development. For manual deployment to AWS as well as for updating dependencies, 
you will need to install [Node](https://nodejs.org/en/), 
[npm](https://docs.npmjs.com/downloading-and-installing-node-js-and-npm), 
and [AWS CLI](https://docs.aws.amazon.com/cli/latest/userguide/getting-started-install.html), 
configuring with your own AWS credentials.

### Deployment

This project currently has two stages, `dev` (currently treated as the production stage) and `test`. 
For manual deployment on your local machine, you'll need to fill out the 
`public_key` and `secrets.json` with the required information, and install packages:

```
npm install
serverless plugin install --name serverless-python-requirements
```

To deploy, run:

```
serverless deploy --stage {stage}
```

### Testing

Instructions to manually run tests will be detailed here.

## Job Syntax

Jobs are stored as entries in a dynamodb table. They can be thought of as json objects. Here is an example: 

```json
{
  "action": "expose",
  "deviceInstance": "camera1",
  "deviceType": "camera",
  "optional_params": {
    "bin": "1,1",
    "count": "1",
    "dither": "off",
    "filter": "air",
    "size": "100%",
    "username": "useAuth0"
  },
  "required_params": {
    "image_type": "light",
    "time": "1"
  },
  "secondsUntilComplete": "60",
  "site": "wmd",
  "statusId": "RECEIVED#01DZVY846T52P6P3JWAJNJMJ1Z",
  "timestamp_ms": 1580411916506,
  "ulid": "01DZVY846T52P6P3JWAJNJMJ1Z",
  "user_name": "my-username",
  "user_id": "convoluted-user-id12349876"
}
```
The keys are described as follows: 
- **action**: the command to be completed.
- **deviceInstance**: name of the specific device for the job
- **deviceType**: the generic type of device for the job
- **optional_params**: command-specific optional information
- **required_params**: command-specific required information
- **secondsUntilComplete**: estimate of the seconds until the job status is marked "COMPLETE".
- **site**: site abbreviation
- **statusId**: string concatenation of `{jobStatus}#{ulid}`
- **ulid**: unique lexicographically-sortable id. Sorting by this string will place jobs in the order they were issued. For more info: https://github.com/ulid/spec
- **user_name**: the username that is typically displayed to the user.
- **user_id**: unique identification for the user. Stored as 'sub' in auth0.

## Endpoints

All of the following endpoints use the base url `https://jobs.photonranch.org/jobs`

- POST `/newjob`
    - Description: Request a new job for an observatory to complete, typically from the UI. 
    - Authorization required: yes (header must contain Bearer access token from Auth0)
    - Query Params: none 
    - Request body: 
        - "site" | string | site abbreviation
        - "device" | string | type of device 
        - "instance" | string | name of the device 
        - "action" | string | name of the job
        - "required_params" | json | additional parameters for the job
        - "optional_params" | json | additional parameters for the job
        - "user_name" | string | the readable username, used for display
        - "user_id" | string | unique id for the user
    - Responses: 
        - 200: returns a copy of the job that was added to the jobs database
        - 400: missing required key in body
        - 401: unauthorized user (either not logged in or did not reserve time) 

- POST `/updatejobstatus`
    - Description: Update the status of a job, mainly used by observatory code. 
    This status is typically displayed in the UI for the user to see what is currently happening. 
    - Authorization required: no (will be added later)
    - Query Params: none
    - Request body: 
        - "site" | string | site abbreviation
        - "ulid" | string | id of the job being updated
        - "newStatus" | string | new status, for example: "STARTED", "EXPOSING", "COMPLETE".
        - "secondsUntilComplete" | int | estimate of the remaining time until a future status update of "complete" is sent. An empty value will register as -1. If no time estimate is available, use value of -1.
    - Responses: 
        - 400: missing required parameter (site and job ulid) 
        - 200: returns a JSON body with updated ulid, statusID, and secondsUntilComplete
    - Example request:
    ```python
    # python 3.6
    import requests, json
    url = "https://jobs.photonranch.org/jobs/updatejobstatus"
    payload = json.dumps({
        "site": "wmd",
        "ulid": "01E4C33S9ZFGS8P0K31FH9FDTN",
        "newStatus": "STARTED",
        "secondsUntilComplete": 5
    })
    response = requests.request("POST", url, data=payload)
    print(response.json())
    ```
    - Example response:
    ```python
    {
        'ResponseMetadata': {
            'RequestId': '5UJ90INAI48OD0TPC7LVHK85R3VV4KQNSO5AEMVJF66Q9ASUAAJG', 
            'HTTPStatusCode': 200, 
            'HTTPHeaders': {
                'server': 'Server', 
                'date': 'Thu, 
                26 Mar 2020 21:41:37 GMT', 
                'content-type': 'application/x-amz-json-1.0', 
                'content-length': '2', 
                'connection': 'keep-alive', 
                'x-amzn-requestid': '5UJ90INAI48OD0TPC7LVHK85R3VV4KQNSO5AEMVJF66Q9ASUAAJG', 
                'x-amz-crc32': '2745614147'
            }, 
            'RetryAttempts': 0
        }
    }
    ```
    - The job in dynamodb has been updated to look like:
    ```json
    [
        {
            "statusId": "STARTED#01E4C33S9ZFGS8P0K31FH9FDTN",
            "action": "move_relative",
            "deviceType": "focuser",
            "required_params": {
                "position": "1"
            },
            "ulid": "01E4C33S9ZFGS8P0K31FH9FDTN",
            "timestamp_ms": 1585248855359,
            "deviceInstance": "focuser1",
            "secondsUntilComplete": 5,
            "site": "wmd",
            "optional_params": {},
            "user_name": "Firstname Lastname",
            "user_id": "user-id-1234"
        }
    ]
    ```
  
- POST `/getnewjobs`
    - Description: get a list of jobs with status "UNREAD". These jobs are immediately updated with a status of "RECEIVED". 
    - Authorization required: no (will be added later)
    - Request body: 
        - "site" | string | site abbreviation
    - Responses: 
        - 200: List of updated job objects (JSON). See 'Job Syntax' above for an example.
    - Example request: 
    ```python
    # python 3.6
    import requests, json
    url = "https://jobs.photonranch.org/jobs/getnewjobs"
    payload = json.dumps({"site": "wmd"})
    response = requests.request("POST", url, data=payload)
    print(response.json())
    ```
    - Example response: 
    ```json
    [
        {
            "statusId": "UNREAD#01E4C33S9ZFGS8P0K31FH9FDTN",
            "action": "move_relative",
            "deviceType": "focuser",
            "required_params": {
                "position": "1"
            },
            "ulid": "01E4C33S9ZFGS8P0K31FH9FDTN",
            "timestamp_ms": 1585248855359,
            "deviceInstance": "focuser1",
            "site": "wmd",
            "optional_params": {},
            "user_name": "Firstname Lastname",
            "user_id": "user-id-1234"
        },
        {
            "statusId": "UNREAD#01E4C34DEK5H1CMJEPJ2N5AX02",
            "action": "stop",
            "deviceType": "camera",
            "required_params": {},
            "ulid": "01E4C34DEK5H1CMJEPJ2N5AX02",
            "timestamp_ms": 1585248875987,
            "deviceInstance": "camera1",
            "site": "wmd",
            "optional_params": {},
            "user_name": "Firstname Lastname",
            "user_id": "user-id-1234"
        }
    ]
    ```

- POST `/getrecentjobs`
    - Description: return a list of jobs that are no older than the provided length of time.
    - Authorization required: no (will be added later)
    - Request body: 
        - "site" | string | site abbreviation
        - "timeRange" | int | maximum age of jobs returned, *in milliseconds*
    - Responses: 
        - 200: List of job objects (JSON) younger than maximum age. See 'Job Syntax' 
        above for an example.
    - Example request: 
    ```python
    # python 3.6
    import requests, json
    url = "https://jobs.photonranch.org/jobs/getrecentjobs"
    payload = json.dumps({
        "site": "wmd", 
        "timeRange": 1000 * 60 * 60 * 24, # get anything less than a day old (using milliseconds)
    })
    response = requests.request("POST", url, data=payload)
    print(response.json())
    ```
    - Example response: 
    ```json
    [
        {
            "statusId": "UNREAD#01E4C33S9ZFGS8P0K31FH9FDTN",
            "action": "move_relative",
            "deviceType": "focuser",
            "required_params": {
                "position": "1"
            },
            "ulid": "01E4C33S9ZFGS8P0K31FH9FDTN",
            "timestamp_ms": 1585248855359,
            "deviceInstance": "focuser1",
            "site": "wmd",
            "optional_params": {},
            "user_name": "Firstname Lastname",
            "user_id": "user-id-1234"
        }
    ]
    ```

## License