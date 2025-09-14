"""
Script to notify Jira and Slack of pipeline result.
Requires: jira, requests (pip install jira requests)
Environment variables:
  JIRA_URL, JIRA_USER, JIRA_API_TOKEN, JIRA_TICKET, PIPELINE_URL, AGENT_VERSION, PIPELINE_STATUS, SLACK_WEBHOOK_URL
"""
import os
import requests
from jira import JIRA

JIRA_URL = os.environ["JIRA_URL"]
JIRA_USER = os.environ["JIRA_USER"]
JIRA_API_TOKEN = os.environ["JIRA_API_TOKEN"]
JIRA_TICKET = os.environ["JIRA_TICKET"]
PIPELINE_URL = os.environ.get("PIPELINE_URL", "")
AGENT_VERSION = os.environ.get("AGENT_VERSION", "")
PIPELINE_STATUS = os.environ.get("PIPELINE_STATUS", "FAILED")
SLACK_WEBHOOK_URL = os.environ["SLACK_WEBHOOK_URL"]

jira = JIRA(server=JIRA_URL, basic_auth=(JIRA_USER, JIRA_API_TOKEN))

if PIPELINE_STATUS == "SUCCESS":
    msg = f"✅ Agent installer version {AGENT_VERSION} validated and promoted to production.\nPipeline: {PIPELINE_URL}"
else:
    msg = f"❌ Agent installer version {AGENT_VERSION} failed validation.\nPipeline: {PIPELINE_URL}"

jira.add_comment(JIRA_TICKET, msg)

slack_msg = {
    "text": msg
}
requests.post(SLACK_WEBHOOK_URL, json=slack_msg)