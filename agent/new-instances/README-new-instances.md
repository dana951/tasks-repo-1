# Agent Installation Flow for New EC2 Instances

## Overview

This document describes the automated process for deploying the security agent on **new EC2 instances**. The design leverages an Ansible role and a post-configuration playbook, both executed at instance launch via user data. The agent installer is **decoupled from the AMI** and resides in an S3 bucket, allowing for rapid updates and simplified maintenance.

---

## Flow Summary

1. **AMI Preparation**
   - The base AMI is built with Packer and includes Ansible and other required tools, but **does not include the agent installer**.

2. **Instance Launch**
   - When a new EC2 instance is provisioned (e.g., via Terraform), the user data script triggers the execution of the `post-config.yml` Ansible playbook.

3. **Ansible Role Execution**
   - The `post-config.yml` playbook includes a dedicated Ansible role for agent installation.
   - This role:
     - Downloads the latest agent installer from a predefined S3 bucket.
     - Executes the installer to deploy the agent.
     - Performs service checks and validation (e.g., ensures the agent service is running, sets up monitoring).

4. **Decoupling the Installer**
   - The agent installer is **not baked into the AMI**. Instead, it is stored in S3.
   - This allows the installer to be updated independently of the AMI, accommodating frequent version changes without requiring new AMI builds.

5. **Benefits**
   - **Maintainability:** The agent installer can be updated at any time by uploading a new version to S3.
   - **Simplicity:** No need to rebuild or redeploy AMIs for agent updates.
   - **Automation:** The entire installation and validation process is automated and runs at instance launch.

---

## Example Flow

1. **Provision new EC2 instance** (e.g., via Terraform).
2. **User data** runs at boot, triggering the Ansible `post-config.yml` playbook.
3. **Ansible role** downloads the agent installer from S3 and installs the agent.
4. **Validation:** The role checks that the agent service is running and healthy.

---

## Summary

By decoupling the agent installer from the AMI and automating installation with Ansible at instance launch, this process ensures that all new EC2 instances always receive the latest agent version