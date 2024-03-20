#lambda_function.py
# This function is invoked from a Slack slash command
# It verifies the request, responds to it, and invokes the SNS topic for the 
# second lambda function, if required.
# Author: Sara Wood

import json
import hashlib
import hmac
import boto3
from botocore.exceptions import ClientError
import base64
from urllib import parse as urlparse
import time
import os

helper_text = """
Syntax: `/retry <request_string>`

Retry uses the request string to look for any matching records on Bamboo HR to retry synchronising employee data.

The synchronisation will update Slack, Gsuite and Jira employee profiles.

Examples:
`/retry @username` retries synchronising by slack username
`/retry <employee_id>` retries synchronising employee by employee_id as listed on Bamboo HR
`/retry --email <user@auth0.com>` retries synchronising employee by work email
`/retry --country <country name>` retries synchronising employees by country
`/retry --department <department name>` retries synchronising employees by department
`/retry --division <division name>` retries synchronising employees by division
`/retry --hireDate YYYY-MM-DD` retries synchronising employees by hire date
`/retry --all` retries synchronising ALL employees (use with caution)
"""


# Simple notification service ARN
SNS_TOPIC_ARN = 'arn:aws:sns:us-east-1:xxxxxx:slackapp_run_retrySync'
SLACK_CHANNEL_ID = "xxxxxx"

def lambda_handler(event, context):
    
    request_body = event["body"]
    request_body_parsed = dict(urlparse.parse_qsl(request_body))

    
    channel_id = request_body_parsed["channel_id"]
    
    if channel_id == SLACK_CHANNEL_ID:
        delivered_signature = event["headers"]['X-Slack-Signature']

        slack_request_timestamp = event["headers"]['X-Slack-Request-Timestamp']

        slack_signing_secret = getParameter('retry_sync_slackapp_secret')
        
        basestring = f"v0:{slack_request_timestamp}:{request_body}".encode('utf-8')
        
        slack_signing_secret = bytes(slack_signing_secret, 'utf-8')
        expected_signature = 'v0=' + hmac.new(slack_signing_secret, basestring, hashlib.sha256).hexdigest()
            
        current_time = time.time()
        slack_request_timestamp_asFloat = float(slack_request_timestamp)
        
        if (current_time - slack_request_timestamp_asFloat) > 300:
            response_text = "Message more than 5 minutes old"
            response_code = 412
        # Confirm that delivered signature is the same as the expected_signature
        elif hmac.compare_digest(expected_signature, delivered_signature):  
            try: 
                search_string = request_body_parsed["text"]
            except KeyError:
        	    # catches if no search string parameter is provided
                search_string = ""
            # hooray, signature strings match, the request came from Slack!
            if search_string == "" or search_string == "help":
                response_text = helper_text
                response_code = 200
            else: 
                response_text = ":female-detective::skin-tone-3: looking up _" + search_string + "_..."
                response_code = 200
                # Publish to the SNS topic
                client = boto3.client('sns')
                trigger = client.publish(TargetArn = SNS_TOPIC_ARN,Message=json.dumps({'default': json.dumps(request_body_parsed)}),MessageStructure='json') 
        else:
            response_text = "Message signature is invalid"
            response_code = 412
    else:
        response_text = ":warning: You must use `/retry` while inside an authorized channel."
        # Returning status code of 200 so that response text is presented to user
        response_code = 200

    return {
        'statusCode': response_code,
        'body': response_text
    }
    
            
def getParameter(param_name):
    session = boto3.Session(region_name='us-east-1')
    ssm = session.client('ssm')
    response = ssm.get_parameter(Name=param_name,WithDecryption=True)
    return response['Parameter']['Value']
