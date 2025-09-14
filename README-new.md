# Decoupled Agent Installation Design

## Overview

This document describes the improved, maintainable, and automated process for deploying a security agent on new EC2 instances in production. The design decouples the agent installation logic from the AMI by using a version-controlled shell script, stored in S3 alongside the agent installer. This approach allows for rapid updates to the installation process without requiring AMI rebuilds, and ensures all changes are tracked, tested, and auditable.

---

## Key Design Decisions

### 1. **Decoupled Shell Script**

- The **agent installation shell script** is **not baked into the AMI**.
- The script is stored in a dedicated S3 bucket, in the same folder as the agent installer file.
- There is a **strong correlation** between the shell script and the installer: they are always updated and deployed together.
- The shell script is version-controlled in a Git repository, ensuring all changes are tracked, reviewed, and auditable.

### 2. **Ansible Role in the AMI**

- The AMI contains an **Ansible role** that is responsible for:
  - Downloading the latest shell script from the S3 bucket.
  - Executing the shell script to perform the agent installation.
  - Performing service checks and health validation using handlers (e.g., systemd reload/restart) as previously designed.
- **Difference from previous design:**  
  Instead of running the agent installer directly in the playbook, the playbook now downloads and runs the shell script, which encapsulates the installation logic. This means changes to the installation process do not require changes to the AMI or the baked-in Ansible role.

### 3. **Version Control and Pipeline**

- The shell script is maintained in a **Git repository**.
- The repository includes a **CI/CD pipeline** (e.g., GitLab CI) that:
  - Validates the shell script and agent installer.
  - Ensures both files are present and compatible.
  - Uploads both the shell script and the agent installer to the S3 bucket if validation passes.
  - Fails and notifies relevant teams if validation does not pass.

---

## Automated Update and Deployment Flow

### 1. **SOC Provides New Agent Installer**

- When a new agent installer is available, the SOC team uploads it to a dedicated Jira ticket as a comment, following a strict format (e.g., `AGENT-VERSION: <version>`).
- The installer file is attached to the comment or ticket.

### 2. **Pipeline Trigger**

- A **Jira webhook** or integration triggers the GitLab pipeline when a new comment/attachment is added.
- The pipeline fetches the new installer from Jira.

### 3. **Validation Step**

- The pipeline checks:
  - Only the expected files are present (installer and shell script).
  - If extra files (e.g., a new config file) are present, the pipeline fails, comments on the Jira ticket, and notifies the SOC Slack channel, instructing SOC to open a DevOps ticket for further action.

### 4. **Automated Testing**

- The pipeline:
  - Launches a test EC2 instance in a staging account using the latest production-like AMI.
  - Runs the Ansible role, which downloads and executes the shell script.
  - The shell script installs the agent and performs health checks (e.g., service status, `--last-checkin` command).
  - If all checks pass, the pipeline tears down the instance.

### 5. **Upload and Notification**

- If tests pass:
  - The pipeline uploads both the shell script and the agent installer to the S3 bucket.
  - Updates the Jira ticket with a success comment and pipeline link.
  - Notifies the SOC Slack channel.
- If tests fail:
  - The pipeline tears down the instance.
  - Comments on the Jira ticket with failure details and pipeline link.
  - Notifies the SOC Slack channel.

---

## Ansible Role: `--test` Flag

- The Ansible role that runs the shell script can accept a `--test` flag (default: `false`).
- When `--test` is `true`, the shell script should run in test mode (e.g., perform dry-run checks, skip actual installation, or run extra validation).
- This allows for safer testing and validation during pipeline runs or troubleshooting.

---

## Benefits of This Design

- **Maintainability:** Changes to the installation process require only updates to the shell script and pipeline, not the AMI.
- **Auditability:** All changes are tracked in Git and Jira, with automated notifications and logs.
- **Safety:** Automated testing in a staging environment ensures only working installers/scripts are promoted to production.
- **Separation of Duties:** SOC provides the installer; DevOps maintains the shell script and automation.
- **Rapid Updates:** New agent versions or installation logic can be rolled out quickly and safely.

---

## Summary

This process ensures a robust, maintainable, and auditable workflow for agent deployment on new EC2 instances, with clear separation of responsibilities, automated validation, and rapid response to changes in