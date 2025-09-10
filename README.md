# tasks-repo-1

## Overview

This repository contains automation for deploying a security agent and monitoring setup on all EC2 instances across production AWS accounts. The solution is divided into two main use cases:

1. **Deploying the agent and monitoring on existing EC2 instances**
2. **Deploying the agent and monitoring on newly created EC2 instances (as part of customer provisioning or upgrade processes)**

This README focuses on the **existing instances** use case.

---

## Background

All production EC2 instances are launched from pre-built AMIs. These AMIs are created via a dedicated pipeline using **Packer** and **Ansible** for configuration management. The AMIs already include:

- Ansible installed
- node_exporter
- process_exporter
- SSM Agent (via Amazon Linux base AMI)

Additionally, the provisioning process (using Terraform) ensures that each instance has an IAM Role with the `AmazonEc2RoleForSSM` policy attached, enabling SSM management.

---

## Solution Approach

### Why SSM?

AWS Systems Manager (SSM) is a regional service that allows you to run commands in bulk on EC2 instances and collect per-instance results. This makes it ideal for orchestrating agent deployment and monitoring setup across all regions and instances.

### Ansible Document & S3

- The Ansible playbook (see [`agent/existing-instances/playbook.yml`](agent/existing-instances/playbook.yml)) and the agent installer are stored in a dedicated S3 bucket in each production account.
- The SSM document references this playbook and installer for execution on target instances.

### Gradual, Controlled Rollout

Since this is a production change, deployments are performed **gradually**:
- Start with a small subset of instances.
- Increase the rollout as confidence grows.
- The automation supports specifying the number or percentage of instances to target in each run.

---

## Implementation Steps

### 1. Ansible Playbook

- The playbook (`playbook.yml`) is designed to:
  - Download and install the security agent.
  - Set up a custom metric for node_exporter to monitor agent health.
  - Configure cron jobs for ongoing metric updates.
  - Ensure node_exporter is properly configured and reloaded.

### 2. Python Automation

- The Python script (`python-ssm.py`) provides:
  - **Bulk SSM execution**: Run the Ansible document on selected instances in each region.
  - **State management**: Track which instances succeeded, failed, or are pending.
  - **Reporting**: Generate progress reports across all regions.
  - **Gradual rollout**: Specify the number or percentage of instances to target per run.
  - **Locking and logging**: Prevent concurrent runs and maintain detailed logs.

---

## How to Use

1. **Prepare S3 Buckets**  
   - Upload the Ansible playbook and agent installer to a dedicated S3 bucket in each production account.

2. **Configure SSM Document**  
   - Register an SSM document that references the Ansible playbook in S3.

3. **Run the Python Automation**  
   - Use the CLI to generate reports, deploy to instances, and monitor progress.
   - Example:
     ```sh
     python3 python-ssm.py report --profile <aws-profile> --bucket <s3-bucket>
     python3 python-ssm.py ssm --profile <aws-profile> --bucket <s3-bucket> --region <region> --count 10
     ```

4. **Monitor and Gradually Increase Rollout**  
   - Start with a small batch, review results, and increase the rollout as needed.

---

## Files

- [`agent/existing-instances/playbook.yml`](agent/existing-instances/playbook.yml): Ansible playbook for agent installation and monitoring setup.
- [`agent/existing-instances/python-ssm.py`](agent/existing-instances/python-ssm.py): Python automation for SSM-based deployment, state management, and reporting.

---

## Notes

- The automation assumes all target instances are SSM-managed and have the necessary IAM permissions.
- The solution is designed for **safe, gradual, and observable** production changes.



