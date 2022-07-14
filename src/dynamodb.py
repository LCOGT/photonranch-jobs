
import boto3
import os
from boto3.dynamodb.conditions import Attr, Key
import ulid
import time

dynamodb = boto3.resource('dynamodb')
table = dynamodb.Table(os.getenv('DYNAMODB_JOBS', 'photonranch-jobs-dev'))
#table = dynamodb.Table(os.environ['DYNAMODB_JOBS'])

def get_all_site_jobs(site: str, job_id: str) -> list:
    # job_id will be excluded from the search

    query = table.query(
        ProjectionExpression="site, ulid, device",
        KeyConditionExpression=Key('site').eq(site) & Key('ulid').lt(job_id),
    )
    site_jobs = query['Items']
    return site_jobs

def remove_jobs(jobs: list):

    with table.batch_writer() as batch:
        for job in jobs:
            key = {
                'site': job['site'],
                'ulid': job['ulid']
            }
            batch.delete_item(Key=key)

if __name__ == "__main__":
    site = 'tst'
    ulid = ulid.new().str
    all_jobs = get_all_site_jobs(site, ulid)


    to_remove = all_jobs
    print(to_remove, len(all_jobs))

    #remove_jobs(to_remove)

    all_jobs = get_all_site_jobs(site, ulid)
    print(len(all_jobs))
    
    
     
