# photonranch-jobs

This repository manages job requests between the web UI and the observatory site software.

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
  "site": "wmd",
  "statusId": "RECEIVED#01DZVY846T52P6P3JWAJNJMJ1Z",
  "timestamp_ms": 1580411916506,
  "ulid": "01DZVY846T52P6P3JWAJNJMJ1Z"
}
```
The keys are described as follows: 
- **action**: the command to be completed.
- **deviceInstance**: name of the specific device for the job
- **deviceType**: the generic type of device for the job
- **optional_params**: command-specific optional information
- **required_params**: command-specific required information
- **site**: site abbreviation
- **statusId**: string concatenation of `{jobStatus}#{ulid}`
- **ulid**: unique lexicographical id. Sorting by this string will place jobs in the order they were issued. 

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
    - Response data: returns a copy of the job that was added to the jobs database. 

- POST `/updatejobstatus`
    - Description: Update the status of a job. This status is typically displayed in the UI for the user to see what is currently happening. 
    - Authorization required: no (will be added later)
    - Query Params: none
    - Request body: 
        - "site" | string | site abbreviation
        - "ulid" | string | id of the job being updated
        - "newStatus" | string | new status, for example: "STARTED", "EXPOSING", "COMPLETE".
        - "secondsUntilComplete" | int | estimate of the remaining time until a future status update of "complete" is sent. An empty value will register as -1. If no time estimate is available, use value of -1. 
    - Response data: 200 if successful
    
- POST `/getnewjobs`
    - Description: get a list of jobs with status "UNREAD". These jobs are immediately updated with a status of "RECEIVED". 
    - Authorization required: no (will be added later)
    - Query Params: none
    - Request body: 
        - "site" | string | site abbreviation
    - Response data: List of job objects (json). See 'Job Syntax' above for an example.

- POST `/getrecentjobs`
    - Description: return a list of jobs that are no older than the provided length of time.
    - Authorization required: no (will be added later)
    - Query Params: none
    - Request body: 
        - "site" | string | site abbreviation
        - "timeRange" | int | maximum age of jobs returned, *in milliseconds*
    - Response data: List of job objects (json). See 'Job Syntax' above for an example.