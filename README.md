# Photon Ranch Jobs

This repository manages job requests between the web UI and the observatory site software.

## Description

Users can create new job requests, such as pointing a mount or exposing a camera,
which observatories can then carry out.

Observatories can retrieve new jobs to perform, update a job's status as it changes, and retrieve recent jobs regardless of status. Use of these API endpoints is mostly found in
[the observatory repository](https://github.com/LCOGT/ptr-observatory).

## Local Development

Clone the repository to your local machine:

```bash
$ git clone https://github.com/LCOGT/photonranch-jobs.git
$ cd photonranch-jobs
```

### Requirements

You will need the [Serverless Framework](https://www.serverless.com/framework/docs/getting-started)
installed locally for development. For manual deployment to AWS as well as for updating dependencies,
you will need to install [Node](https://nodejs.org/en/),
[npm](https://docs.npmjs.com/downloading-and-installing-node-js-and-npm),
and [AWS CLI](https://docs.aws.amazon.com/cli/latest/userguide/getting-started-install.html),
configuring with your own AWS credentials.

### Deployment

This project currently has two stages, `prod` and `dev`. Changes to the main or dev branch will automatically deploy
to the corresponding stage environment. It is recommended that any updates are deployed by this mechanism.
For manual deployment on your local machine, you'll need to fill out the
`public_key` and `secrets.json` with the required information, and install packages:

```bash
$ npm install -global serverless 
$ serverless plugin install --name serverless-python-requirements
$ serverless plugin install --name serverless-dynamodb-pitr
$ serverless plugin install --name serverless-domain-managerplugin install --name serverless-python-requirements
```

To deploy, run:

```bash
$ serverless deploy --stage {stage}
```

### Testing

Tests are written with pytest, but currently have minimal code coverage. 

## Job Syntax

Jobs are stored as entries in a DynamoDB table. They can be thought of as JSON objects. Here is an example:

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
  "site": "saf",
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
- **ulid**: unique lexicographically-sortable id. Sorting by this string will place jobs in the order they were issued.
  For more info: <https://github.com/ulid/spec>
- **user_name**: the username that is typically displayed to the user.
- **user_id**: unique identification for the user. Stored as 'sub' in auth0.

## Endpoints

All of the following endpoints use the base URL `https://jobs.photonranch.org/{stage}` where `{stage}` is either `dev`
for the dev environment, or `jobs` for the production version.

- POST `/newjob`
  - Description: Request a new job for an observatory to complete, typically from the UI.
  - Authorization required: Yes (header must contain Bearer access token from Auth0).
  - Query Params: None.
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
    - 200: Returns a copy of the job that was added to the jobs database.
    - 400: Missing required key in body.
    - 401: Unauthorized user (either not logged in or did not reserve time).

- POST `/updatejobstatus`
  - Description: Update the status of a job, mainly used by observatory code.
    This status is typically displayed in the UI for the user to see what is currently happening.
  - Authorization required: No (will be added later).
  - Query Params: None.
  - Request body:
    - "site" | string | site abbreviation
    - "ulid" | string | id of the job being updated
    - "newStatus" | string | new status, for example: "STARTED", "EXPOSING", "COMPLETE".
    - "secondsUntilComplete" | int | estimate of the remaining time until a future status update of "complete" is sent. An empty value will register as -1. If no time estimate is available, use value of -1.
    - "alternateQueue" | bool | whether to update the job status in the primary or alternate queue. Default is false.
  - Responses:
    - 400: Missing required parameter (site and job ulid).
    - 200: Returns a JSON body with updated ulid, statusID, and secondsUntilComplete.
  - Example request:

    ```python
    # python 3.7
    import requests, json
    url = "https://jobs.photonranch.org/jobs/updatejobstatus"
    payload = json.dumps({
        "site": "saf",
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

  - The job in DynamoDB has been updated to look like:

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
            "site": "saf",
            "optional_params": {},
            "user_name": "Firstname Lastname",
            "user_id": "user-id-1234"
        }
    ]
    ```
  
- POST `/getnewjobs`
  - Description: Get a list of jobs with status "UNREAD". These jobs are immediately updated with a status of "RECEIVED".
  - Authorization required: No (will be added later).
  - Request body:
    - "site" | string | site abbreviation
    - "alternateQueue" | bool | whether to get new jobs from the alternate queue as opposed to the primary one. An
      operation on one queue will not affect the other. Default is false.
  - Responses:
    - 200: List of updated job objects (JSON). See 'Job Syntax' above for an example.
  - Example request:

    ```python
    # python 3.7
    import requests, json
    url = "https://jobs.photonranch.org/jobs/getnewjobs"
    payload = json.dumps({"site": "saf"})
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
            "site": "saf",
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
            "site": "saf",
            "optional_params": {},
            "user_name": "Firstname Lastname",
            "user_id": "user-id-1234"
        }
    ]
    ```

- POST `/getrecentjobs`
  - Description: Return a list of jobs that are no older than the provided length of time.
  - Authorization required: No (will be added later).
  - Request body:
    - "site" | string | site abbreviation
    - "timeRange" | int | maximum age of jobs returned, *in milliseconds*
  - Responses:
    - 200: List of job objects (JSON) younger than maximum age. See 'Job Syntax'
        above for an example.
  - Example request:

    ```python
    # python 3.7
    import requests, json
    url = "https://jobs.photonranch.org/jobs/getrecentjobs"
    payload = json.dumps({
        "site": "saf", 
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
            "site": "saf",
            "optional_params": {},
            "user_name": "Firstname Lastname",
            "user_id": "user-id-1234"
        }
    ]
    ```
