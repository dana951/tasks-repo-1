# README-jira-new-process.md

## Security Agent Installer Promotion Process

This document defines the end-to-end process for securely and reliably promoting a new security agent installer version from the SOC team to S3 buckets in all production AWS accounts, using Jira for workflow management and GitLab CI/CD for automation.

---

### **Process Overview**

1. **New Agent Installer Availability**
   - SOC team prepares a new agent installer version.
   - The installer is uploaded to a dedicated S3 bucket in the SOC AWS account at a path like:  
     `SOC-AGENT-BUCKET/agent/v<version>/agent-installer.sh`
   - The S3 bucket has a resource policy (to be defined) allowing cross-account access for DevOps.

2. **Jira Issue Creation**
   - DevOps team uses a Jira project named **Devops** with a Kanban board.
   - A custom issue type **"Security Agent Deploy Request"** is used.
   - This issue type has a mandatory field **Agent-Version** (format: `x.x.x`, e.g., `1.0.0`).
   - Workflow statuses: **ToDo**, **In Progress**, **Done**, **Info Needed**, **Failed**, **Canceled**.
     - On creation: status is **ToDo**.
     - If field validation fails: status is **Info Needed**.
     - From **Info Needed**: can move to **ToDo** or **Canceled**.
     - From **ToDo**: can move to **Info Needed** or **In Progress**.
     - From **In Progress**: can move to **Done** or **Failed**.
     - From **Failed**: can move to **ToDo** or **Canceled**.

3. **SOC Team Action**
   - After uploading the installer to S3, SOC creates a "Security Agent Deploy Request" issue in Jira.
   - Sets the **Agent-Version** field to the new version.

4. **Issue Assignment**
   - **Open Issue:** Who should the issue be assigned to on creation?  
     - Options: a "jira-bot" user, DevOps team lead, or current DevOps on-call.  
     - **Recommendation:** Assign to a "jira-bot" user for automation, and reassign only on failure or manual intervention.

5. **Jira Automation**
   - When a new "Security Agent Deploy Request" issue is created with status **ToDo**:
     - Validate the **Agent-Version** field format.
     - If invalid:
       - Status → **Info Needed**
       - Assign to the issue creator (SOC member).
       - Add comment: "Please provide a valid Agent-Version (format: x.x.x)."
     - If valid:
       - Trigger the GitLab pipeline (see next step).
       - (Assignment: see above.)

6. **GitLab Pipeline Trigger**
   - Jira automation triggers the GitLab pipeline via webhook.
   - **Open Issue:**  
     - Use a GitLab project access token (not a personal token) for security.
     - Should a dedicated GitLab user be created for this automation?  
       - **Recommendation:** Use a project access token with minimal permissions.

7. **GitLab Runner & AWS Roles**
   - The pipeline runs on a self-hosted GitLab runner in the DevOps AWS account.
   - The runner uses a role (Runner-Role) that can assume the **Agent-Deploy** role.
   - **Agent-Deploy** role has permissions to:
     - Fetch the agent installer from the SOC S3 bucket (cross-account).
     - Upload the installer to the DevOps test S3 bucket.
   - S3 bucket policies must allow these actions (to be defined).

8. **Pipeline Steps**
   1. **Assume Agent-Deploy Role**
   2. **Fetch agent installer** from SOC S3 bucket.
   3. **Upload installer** to DevOps test S3 bucket.
   4. **Terraform:** Launch EC2 in test account with user data to:
      - Download installer from test S3 bucket.
      - Set exec permissions.
      - Run installer.
      - Verify agent service is running.
      - Verify agent version matches **Agent-Version** field.
   5. **If all checks pass:**
      - Upload installer to each production account S3 bucket.
      - Update a manifest file in each bucket (JSON structure to be defined) with:
        - Agent version
        - Date uploaded
        - Pipeline link
      - Update Jira issue: add success comment, set status to **Done**.
   6. **If any check fails:**
      - Update Jira issue: add failure comment, set status to **Failed**.
      - **Open Issue:** Who should the issue be assigned to on failure?  
        - **Recommendation:** Assign to DevOps on-call for investigation.
      - **Open Issue:** Should a Slack notification be sent?  
        - If yes, to which channel (SOC, DevOps, or both)?  
        - **Recommendation:** Notify both teams for visibility.

9. **Manifest File Structure**
   - **Open Issue:** Should be a JSON file.  
     - Example structure:
       ```json
       {
         "version": "1.0.0",
         "uploaded_at": "2025-09-14T12:34:56Z",
         "pipeline_url": "https://gitlab.com/your-org/your-project/-/pipelines/123456"
       }
       ```
   - This file provides traceability for all agent versions deployed.

10. **Concurrency Control**
    - Only one pipeline should run at a time to prevent race conditions.
    - Use a lock mechanism in the pipeline (e.g., GitLab `resource_group` or custom S3 lock file).

---

### **Open Issues / Decisions Needed**

- **Issue Assignment:**  
  - Who should own the Jira issue at each step?  
  - Recommendation: Use "jira-bot" for automation, assign to SOC on Info Needed, assign to DevOps on failure.

- **Slack Notifications:**  
  - Should failures (and/or successes) be notified in Slack?  
  - Which channel(s) should be notified?

- **Manifest File:**  
  - Confirm JSON structure and required fields.

- **Pipeline Token:**  
  - Use a GitLab project access token for triggering the pipeline from Jira automation.

- **S3 & IAM Policies:**  
  - Define and implement cross-account S3 bucket policies and IAM role trust relationships.

---

### **Summary**

This process ensures:
- **Traceability:** Every agent version and deployment is tracked in Jira and S3.
- **Automation:** Minimal manual intervention, with clear handoffs on failure.
- **Security:** Cross-account access is tightly controlled.
- **Visibility:** Jira and (optionally) Slack provide clear status at every step.
- **Reliability:** Only tested installers are promoted to production.

**All open issues should be resolved before the process is considered production-ready.**