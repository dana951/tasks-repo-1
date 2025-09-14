"""
Script to fetch the latest agent installer and version from a Jira ticket.
Requires: jira (pip install jira)
Environment variables:
  JIRA_URL, JIRA_USER, JIRA_API_TOKEN, JIRA_TICKET
Outputs:
  - agent-installer.sh (the installer file)
  - VERSION (the version string)
"""
import os
import re
from jira import JIRA

JIRA_URL = os.environ["JIRA_URL"]
JIRA_USER = os.environ["JIRA_USER"]
JIRA_API_TOKEN = os.environ["JIRA_API_TOKEN"]
JIRA_TICKET = os.environ["JIRA_TICKET"]

jira = JIRA(server=JIRA_URL, basic_auth=(JIRA_USER, JIRA_API_TOKEN))
issue = jira.issue(JIRA_TICKET)

# Find the latest comment with AGENT-VERSION and an attachment
version = None
attachment_id = None
for comment in reversed(issue.fields.comment.comments):
    match = re.search(r'AGENT-VERSION:\s*([^\s]+)', comment.body)
    if match and comment.body and comment.author:
        version = match.group(1)
        # Find attachment in this comment
        for attachment in issue.fields.attachment:
            if attachment.created.startswith(comment.created[:16]):
                attachment_id = attachment.id
                break
        if version and attachment_id:
            break

if not version or not attachment_id:
    raise Exception("Could not find AGENT-VERSION or installer attachment in Jira ticket.")

# Download the attachment
attachment = jira.attachment(attachment_id)
with open("agent-installer.sh", "wb") as f:
    f.write(attachment.get())

with open("VERSION", "w") as f:
    f.write(version + "\n")

print(f"Downloaded agent-installer.sh and found version: {version}")