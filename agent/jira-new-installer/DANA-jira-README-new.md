# Automated Agent Installer Validation and Deployment Process

## Overview

This process ensures that every new agent installer is **automatically validated** in a real environment before being promoted to production, with **zero manual intervention** and full traceability for both SOC and DevOps teams.

---

## Pipeline & Tooling

- The GitLab pipeline uses a **custom Docker image**: `agent-install:latest`.
- This image includes all required tools and dependencies:  
  `python`, `jira`, `requests`, `terraform`, `awscli`, `jq`, etc.
- The image is specified at the pipeline level, so all jobs use the same environment.

---

## Flow Summary

1. **SOC uploads new agent installer to Jira ticket**  
   - Adds a new comment with the installer file attached.
   - Includes the agent `VERSION` in the comment (e.g., `AGENT-VERSION: 1.2.3`).

2. **GitLab pipeline is triggered automatically**  
   - Triggered by a Jira webhook when a new comment/attachment is added.

3. **Pipeline steps:**  
   - **Fetch installer and version:**  
     - Downloads the new installer and parses the `VERSION` from the Jira comment.
   - **Upload to test S3 bucket:**  
     - Uploads the installer to a predefined S3 bucket in the test AWS account.
   - **Provision test EC2 instance with Terraform:**  
     - Uses `main.tf` to create an EC2 instance from the latest AMI in the test account.
     - Passes user data to the instance to:
       1. Download the installer from the test S3 bucket.
       2. Run the installer.
       3. **Robustly verify agent health:**
          - Check agent service status with `systemctl is-active`.
          - Check agent process is running with `pgrep`.
          - Run `agent --version` and compare the output to the `VERSION` provided in Jira.
          - Optionally, check agent logs for errors.
   - **Validation:**  
     - If all checks pass, the pipeline proceeds.
     - If any check fails (e.g., bad installer, service not running, version mismatch), the pipeline fails.

4. **On Success:**  
   - Uploads the validated installer to the production S3 bucket.
   - Adds a **Success** comment to the Jira ticket, including the agent `VERSION` and a link to the GitLab pipeline run.
   - Sends a **success notification** to the SOC Slack channel.

5. **On Failure:**  
   - Adds a **Failed** comment to the Jira ticket, including the agent `VERSION` and a link to the GitLab pipeline run.
   - Sends a **failure notification** to the SOC Slack channel.

---

## Example User Data Script (for EC2)

```bash
#!/bin/bash
set -e
aws s3 cp s3://TEST-AGENT-BUCKET/agent-installer.sh /tmp/agent-installer.sh
aws s3 cp s3://TEST-AGENT-BUCKET/AGENT_VERSION /tmp/AGENT_VERSION
chmod +x /tmp/agent-installer.sh
/tmp/agent-installer.sh

# Check agent service is running and healthy
if ! systemctl is-active --quiet agent; then
  echo "Agent service is not running!"
  exit 1
fi

# Check agent process is running
if ! pgrep -f agent > /dev/null; then
  echo "Agent process is not running!"
  exit 1
fi

# Check agent version
AGENT_VERSION_EXPECTED="$(cat /tmp/AGENT_VERSION)"
AGENT_VERSION_INSTALLED=$(/usr/local/bin/agent --version)
if [[ "$AGENT_VERSION_INSTALLED" != "$AGENT_VERSION_EXPECTED" ]]; then
  echo "Agent version mismatch! Expected: $AGENT_VERSION_EXPECTED, Got: $AGENT_VERSION_INSTALLED"
  exit 1
fi

# Optionally, check agent logs for errors
if grep -i error /var/log/agent/agent.log; then
  echo "Errors found in agent log!"
  exit 1
fi

echo "Agent installation and validation succeeded."
```

---

## Benefits

- **No manual steps:** The entire process is automated from SOC upload to production deployment.
- **Robust validation:** Multiple checks ensure the agent is not just installed, but running and healthy.
- **Validation before production:** Every installer is tested on a fresh EC2 instance before being made available in production.
- **Traceability:** All actions are logged in Jira and GitLab, with clear links and versioning.
- **Rapid feedback:** SOC is notified immediately of success or failure via Jira and Slack.
- **Simplicity:** Unified pipeline image and clear, maintainable flow.

---

## Summary

This process ensures that every new agent installer is **automatically validated** in a real environment before being promoted to production, with **zero manual intervention** and full traceability and confidence for both SOC and DevOps teams.