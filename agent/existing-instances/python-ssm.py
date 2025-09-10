#!/usr/bin/env python3
"""
Deploy Agent Script for Production Instances
--------------------------------------------
This script manages the deployment of a security/monitoring agent on EC2 instances
across production AWS accounts using AWS SSM + Ansible documents.

Key Features:
- State management in S3 (track which instance succeeded/failed).
- Lock mechanism in S3 to avoid concurrent executions.
- Logging of every action (both local and uploaded to S3).
- Reporting of deployment progress (success, failed, unmanaged, pending).
- Ability to target instances in bulk (by count or percentage).
- User confirmation before actual SSM execution.

with shabeng
chmod +x deploy_agent.py
./deploy_agent.py report --profile prod1 --bucket my-prod-bucket

without shabendg
python3 deploy_agent.py report --profile prod1 --bucket my-prod-bucket
"""

import boto3
import botocore
import json
import logging
import sys
import os
from datetime import datetime
import click
from tabulate import tabulate

# ====================================================
# ---- Global S3 Folder Names & Constants ----
# ====================================================
STATE_PREFIX = "state"
LOCK_PREFIX = "locks"
REPORT_PREFIX = "reports"
PYTHON_LOGS_PREFIX = "python-logs"
SSM_OUTPUT_PREFIX = "ssm-output"
ANSIBLE_DOCUMENT_NAME = "YourAnsibleDocumentName"  # <-- Set your Ansible document name here

# ====================================================
# ---- Logging Setup ----
# ====================================================
def setup_logger():
    ts = datetime.utcnow().strftime("%Y%m%d-%H%M%S")
    log_file = f"script-{ts}.log"

    logger = logging.getLogger()
    logger.setLevel(logging.INFO)

    console = logging.StreamHandler(sys.stdout)
    console.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(message)s"))
    logger.addHandler(console)

    fh = logging.FileHandler(log_file)
    fh.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(message)s"))
    logger.addHandler(fh)

    return logger, log_file

logger, log_file = setup_logger()

def upload_log_to_s3(s3, bucket, region):
    try:
        ts = datetime.utcnow().strftime("%Y/%m/%d")
        key = f"{PYTHON_LOGS_PREFIX}/{region}/{ts}/{os.path.basename(log_file)}"
        s3.upload_file(log_file, bucket, key)
        logger.info(f"Uploaded script log to s3://{bucket}/{key}")
    except Exception as e:
        logger.error(f"Failed to upload log to S3: {e}")

# ====================================================
# ---- Lock Management ----
# ====================================================
def acquire_lock(s3, bucket, region):
    key = f"{LOCK_PREFIX}/{region}.lock"
    try:
        s3.head_object(Bucket=bucket, Key=key)
        logger.error(f"Lock exists: {key}, aborting.")
        sys.exit(1)
    except botocore.exceptions.ClientError:
        s3.put_object(Bucket=bucket, Key=key, Body=b"locked")
        logger.info(f"Acquired lock: {key}")
        return key

def release_lock(s3, bucket, key):
    try:
        s3.delete_object(Bucket=bucket, Key=key)
        logger.info(f"Released lock: {key}")
    except Exception as e:
        logger.error(f"Error releasing lock: {e}")

# ====================================================
# ---- State Management ----
# ====================================================
def load_state(s3, bucket, region):
    key = f"{STATE_PREFIX}/region-{region}/instances.json"
    try:
        obj = s3.get_object(Bucket=bucket, Key=key)
        return json.loads(obj["Body"].read())
    except botocore.exceptions.ClientError:
        return {}

def save_state(s3, bucket, region, state):
    key = f"{STATE_PREFIX}/region-{region}/instances.json"
    s3.put_object(Bucket=bucket, Key=key, Body=json.dumps(state, indent=2))
    logger.info(f"Saved state: {key}")

# ====================================================
# ---- Helper Functions ----
# ====================================================
def get_all_instances(ec2_resource):
    """
    Generator yielding all EC2 instance IDs in the region (any state).
    """
    for instance in ec2_resource.instances.all():
        yield instance.id

# Dana - not in use
def get_running_instances(ec2_resource):
    """
    Generator yielding running EC2 instance IDs.
    """
    for instance in ec2_resource.instances.filter(Filters=[{"Name": "instance-state-name", "Values": ["running"]}]):
        yield instance.id

def get_ssm_managed(ssm_client):
    """
    Generator yielding all instance IDs currently managed by SSM.
    """
    paginator = ssm_client.get_paginator("describe_instance_information")
    for page in paginator.paginate():
        for i in page["InstanceInformationList"]:
            yield i["InstanceId"]

def get_regions_with_instances(session):
    """
    Return a list of regions that have at least one EC2 instance.
    """
    ec2_client = session.client("ec2")
    regions = [r["RegionName"] for r in ec2_client.describe_regions(AllRegions=False)["Regions"]]
    regions_with_instances = []
    for region in regions:
        ec2_resource = session.resource("ec2", region_name=region)
        if any(get_all_instances(ec2_resource)):
            regions_with_instances.append(region)
    return regions_with_instances

# ====================================================
# ---- Reporting ----
# ====================================================
def generate_report_all_regions(session, s3, bucket):
    """
    Generate deployment report for all enabled regions with at least one EC2 instance.
    Returns a list of region reports.
    """
    regions = get_regions_with_instances(session)
    reports = []
    for region in regions:
        ec2_resource = session.resource("ec2", region_name=region)
        ssm_client = session.client("ssm", region_name=region)
        all_instances = set(get_all_instances(ec2_resource))
        ssm_instances = set(get_ssm_managed(ssm_client))
        state = load_state(s3, bucket, region)
        success = sum(1 for x in state.values() if x["Status"] == "SUCCEEDED")
        failed = sum(1 for x in state.values() if x["Status"] == "FAILED")
        unmanaged = len(all_instances - ssm_instances)
        pending = len(ssm_instances - set(state.keys()))
        total = len(all_instances)
        report = {
            "region": region,
            "total": total,
            "success": success,
            "failed": failed,
            "unmanaged": unmanaged,
            "pending": pending,
            "uninstalled": failed + unmanaged + pending
        }
        reports.append(report)
    # Save a single report for all regions
    ts = datetime.utcnow().strftime("%Y%m%d-%H%M%S")
    key = f"{REPORT_PREFIX}/all-regions-report-{ts}.json"
    s3.put_object(Bucket=bucket, Key=key, Body=json.dumps(reports, indent=2))
    logger.info(f"Report for all regions saved: s3://{bucket}/{key}")

def print_report_table(reports):
    table = []
    for rep in reports:
        total = rep["total"] or 1  # Avoid division by zero
        row = [
            rep["region"],
            rep["total"],
            f"{rep['success']} ({rep['success']*100//total}%)",
            f"{rep['failed']} ({rep['failed']*100//total}%)",
            f"{rep['unmanaged']} ({rep['unmanaged']*100//total}%)",
            f"{rep['pending']} ({rep['pending']*100//total}%)",
            f"{rep['uninstalled']} ({rep['uninstalled']*100//total}%)",
        ]
        table.append(row)
    headers = ["Region", "Total", "Success", "Failed", "Unmanaged", "Pending", "Uninstalled"]
    print(tabulate(table, headers=headers, tablefmt="pretty"))

# ====================================================
# ---- Running SSM ----
# ====================================================
def run_ssm_on_instances(ssm_client, s3, bucket, region, instances):
    """
    Run SSM document (e.g. Ansible playbook) on a given list of instances.
    Updates state with the results, including S3 links to stdout and stderr logs.
    """
    if not instances:
        logger.info("No instances to run on.")
        return

    ssm_output_prefix = f"{SSM_OUTPUT_PREFIX}/{region}/"
    # Specify the S3 path to your Ansible playbook/document
    ansible_s3_url = f"s3://{bucket}/your-ansible-folder/your-playbook.yml"
    resp = ssm_client.send_command(
        Targets=[{"Key": "InstanceIds", "Values": instances}],
        DocumentName=ANSIBLE_DOCUMENT_NAME,  # This should be the registered SSM document name or ARN
        Comment="Deploy agent via script",
        OutputS3BucketName=bucket,
        OutputS3KeyPrefix=ssm_output_prefix,
        Parameters={
            "PlaybookS3Url": [ansible_s3_url]  # The parameter name depends on your SSM document definition
        }
    )
    command_id = resp["Command"]["CommandId"]
    logger.info(f"SSM command started: {command_id} on {len(instances)} instances")

    waiter = ssm_client.get_waiter("command_executed")
    waiter.wait(CommandId=command_id, InstanceIds=instances)

    state = load_state(s3, bucket, region)
    for inst in instances:
        res = ssm_client.list_command_invocations(CommandId=command_id, InstanceId=inst, Details=True)
        if not res["CommandInvocations"]:
            continue
        status = res["CommandInvocations"][0]["Status"]
        stdout_log_url = f"s3://{bucket}/{ssm_output_prefix}{command_id}/{inst}/awsrunShellScript/0.awsrunShellScript/stdout"
        stderr_log_url = f"s3://{bucket}/{ssm_output_prefix}{command_id}/{inst}/awsrunShellScript/0.awsrunShellScript/stderr"
        entry = {
            "Status": status,
            "CommandId": command_id,
            "LastRun": datetime.utcnow().isoformat(),
            "StdoutLog": stdout_log_url,
            "StderrLog": stderr_log_url
        }
        state[inst] = entry
    save_state(s3, bucket, region, state)

# ====================================================
# ---- CLI Commands ----
# ====================================================
@click.group()
def cli():
    """CLI tool for agent deployment in production"""
    pass

@cli.command()
@click.option("--profile", required=True, help="AWS profile to use")
@click.option("--bucket", required=True, help="S3 bucket for state and logs")
def report(profile, bucket):
    """Generate deployment report for all regions with EC2 instances"""
    session = boto3.Session(profile_name=profile)
    s3 = session.client("s3")
    logger.info(f"Profile={profile}")
    reports = generate_report_all_regions(session, s3, bucket)
    print_report_table(reports)
    logger.info(json.dumps(reports, indent=2))
    if reports:
        upload_log_to_s3(s3, bucket, reports[0]["region"])

@cli.command()
@click.option("--profile", required=True)
@click.option("--bucket", required=True)
@click.option("--region", required=True)
@click.option("--count", default=None, type=int, help="Number of instances to run on")
@click.option("--percent", default=None, type=int, help="Percentage of instances to run on")
def ssm(profile, bucket, region, count, percent):
    """Run SSM agent install on pending instances"""
    session = boto3.Session(profile_name=profile, region_name=region)
    ec2_resource = session.resource("ec2", region_name=region)
    ssm_client = session.client("ssm", region_name=region)
    s3 = session.client("s3", region_name=region)

    lock_key = acquire_lock(s3, bucket, region)
    try:
        all_instances = set(get_all_instances(ec2_resource))
        ssm_instances = set(get_ssm_managed(ssm_client))
        state = load_state(s3, bucket, region)
        pending = [i for i in ssm_instances if i not in state]
        if not pending:
            logger.info("No pending instances found.")
            return
        # Use a generator for pending instances
        pending_gen = (i for i in ssm_instances if i not in state)
        if percent:
            num = max(1, int(sum(1 for _ in pending_gen) * percent / 100))
            # Re-create generator since it was exhausted by sum
            pending_gen = (i for i in ssm_instances if i not in state)
        elif count:
            num = min(count, sum(1 for _ in pending_gen))
            pending_gen = (i for i in ssm_instances if i not in state)
        else:
            logger.error("Must specify --count or --percent")
            return
        # Use islice to take only the needed number of items
        from itertools import islice
        target = list(islice(pending_gen, num))
        logger.info(f"About to run on {len(target)} instances in {region}")
        confirm = input("Continue? (yes/no): ")
        if confirm.lower() != "yes":
            logger.info("Aborted by user")
            return
        run_ssm_on_instances(ssm_client, s3, bucket, region, target)
    finally:
        release_lock(s3, bucket, lock_key)
        upload_log_to_s3(s3, bucket, region)

@cli.command()
@click.option("--profile", required=True)
@click.option("--bucket", required=True)
@click.option("--region", required=True)
def failed(profile, bucket, region):
    """List failed instances"""
    session = boto3.Session(profile_name=profile, region_name=region)
    s3 = session.client("s3", region_name=region)
    state = load_state(s3, bucket, region)
    failed = {k: v for k, v in state.items() if v["Status"] == "FAILED"}
    print(json.dumps(failed, indent=2))

@cli.command()
@click.option("--profile", required=True)
@click.option("--bucket", required=True)
@click.option("--region", required=True)
def unmanaged(profile, bucket, region):
    """List unmanaged instances (any state, not in SSM)"""
    session = boto3.Session(profile_name=profile, region_name=region)
    ec2_resource = session.resource("ec2", region_name=region)
    ssm_client = session.client("ssm", region_name=region)
    all_instances = set(get_all_instances(ec2_resource))
    ssm_instances = set(get_ssm_managed(ssm_client))
    unmanaged = list(all_instances - ssm_instances)
    print(json.dumps(unmanaged, indent=2))

# ====================================================
# ---- Main Entrypoint ----
# ====================================================
if __name__ == "__main__":
    cli()
