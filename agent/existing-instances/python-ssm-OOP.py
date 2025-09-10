#!/usr/bin/env python3
"""
OOP Refactor of Deploy Agent Script for Production Instances
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
from itertools import islice

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

# ====================================================
# ---- OOP Classes ----
# ====================================================

class S3StateManager:
    def __init__(self, s3, bucket):
        self.s3 = s3
        self.bucket = bucket

    def load_state(self, region):
        key = f"{STATE_PREFIX}/region-{region}/instances.json"
        try:
            obj = self.s3.get_object(Bucket=self.bucket, Key=key)
            return json.loads(obj["Body"].read())
        except botocore.exceptions.ClientError:
            return {}

    def save_state(self, region, state):
        key = f"{STATE_PREFIX}/region-{region}/instances.json"
        self.s3.put_object(Bucket=self.bucket, Key=key, Body=json.dumps(state, indent=2))
        logger.info(f"Saved state: {key}")

    def upload_log(self, region):
        try:
            ts = datetime.utcnow().strftime("%Y/%m/%d")
            key = f"{PYTHON_LOGS_PREFIX}/{region}/{ts}/{os.path.basename(log_file)}"
            self.s3.upload_file(log_file, self.bucket, key)
            logger.info(f"Uploaded script log to s3://{self.bucket}/{key}")
        except Exception as e:
            logger.error(f"Failed to upload log to S3: {e}")

class S3LockManager:
    def __init__(self, s3, bucket):
        self.s3 = s3
        self.bucket = bucket

    def acquire_lock(self, region):
        key = f"{LOCK_PREFIX}/{region}.lock"
        try:
            self.s3.head_object(Bucket=self.bucket, Key=key)
            logger.error(f"Lock exists: {key}, aborting.")
            sys.exit(1)
        except botocore.exceptions.ClientError:
            self.s3.put_object(Bucket=self.bucket, Key=key, Body=b"locked")
            logger.info(f"Acquired lock: {key}")
            return key

    def release_lock(self, key):
        try:
            self.s3.delete_object(Bucket=self.bucket, Key=key)
            logger.info(f"Released lock: {key}")
        except Exception as e:
            logger.error(f"Error releasing lock: {e}")

class AWSAgentManager:
    def __init__(self, profile, bucket, region=None):
        self.session = boto3.Session(profile_name=profile, region_name=region)
        self.s3 = self.session.client("s3", region_name=region)
        self.bucket = bucket
        self.region = region
        self.state_mgr = S3StateManager(self.s3, bucket)
        self.lock_mgr = S3LockManager(self.s3, bucket)

    def get_all_instances(self, ec2_resource):
        for instance in ec2_resource.instances.all():
            yield instance.id

    def get_ssm_managed(self, ssm_client):
        paginator = ssm_client.get_paginator("describe_instance_information")
        for page in paginator.paginate():
            for i in page["InstanceInformationList"]:
                yield i["InstanceId"]

    def get_regions_with_instances(self):
        ec2_client = self.session.client("ec2")
        regions = [r["RegionName"] for r in ec2_client.describe_regions(AllRegions=False)["Regions"]]
        regions_with_instances = []
        for region in regions:
            ec2_resource = self.session.resource("ec2", region_name=region)
            if any(self.get_all_instances(ec2_resource)):
                regions_with_instances.append(region)
        return regions_with_instances

    def generate_report_all_regions(self):
        regions = self.get_regions_with_instances()
        reports = []
        for region in regions:
            ec2_resource = self.session.resource("ec2", region_name=region)
            ssm_client = self.session.client("ssm", region_name=region)
            all_instances = set(self.get_all_instances(ec2_resource))
            ssm_instances = set(self.get_ssm_managed(ssm_client))
            state = self.state_mgr.load_state(region)
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
        self.s3.put_object(Bucket=self.bucket, Key=key, Body=json.dumps(reports, indent=2))
        logger.info(f"Report for all regions saved: s3://{self.bucket}/{key}")
        return reports

    def print_report_table(self, reports):
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

    def run_ssm_on_instances(self, region, instances):
        if not instances:
            logger.info("No instances to run on.")
            return

        ssm_client = self.session.client("ssm", region_name=region)
        ssm_output_prefix = f"{SSM_OUTPUT_PREFIX}/{region}/"
        # Specify the S3 path to your Ansible playbook/document
        ansible_s3_url = f"s3://{self.bucket}/your-ansible-folder/your-playbook.yml"
        resp = ssm_client.send_command(
            Targets=[{"Key": "InstanceIds", "Values": instances}],
            DocumentName=ANSIBLE_DOCUMENT_NAME,
            Comment="Deploy agent via script",
            OutputS3BucketName=self.bucket,
            OutputS3KeyPrefix=ssm_output_prefix,
            Parameters={
                "PlaybookS3Url": [ansible_s3_url]  # The parameter name must match your SSM document definition
            }
        )
        command_id = resp["Command"]["CommandId"]
        logger.info(f"SSM command started: {command_id} on {len(instances)} instances")

        waiter = ssm_client.get_waiter("command_executed")
        waiter.wait(CommandId=command_id, InstanceIds=instances)

        state = self.state_mgr.load_state(region)
        for inst in instances:
            res = ssm_client.list_command_invocations(CommandId=command_id, InstanceId=inst, Details=True)
            if not res["CommandInvocations"]:
                continue
            status = res["CommandInvocations"][0]["Status"]
            stdout_log_url = f"s3://{self.bucket}/{ssm_output_prefix}{command_id}/{inst}/awsrunShellScript/0.awsrunShellScript/stdout"
            stderr_log_url = f"s3://{self.bucket}/{ssm_output_prefix}{command_id}/{inst}/awsrunShellScript/0.awsrunShellScript/stderr"
            entry = {
                "Status": status,
                "CommandId": command_id,
                "LastRun": datetime.utcnow().isoformat(),
                "StdoutLog": stdout_log_url,
                "StderrLog": stderr_log_url
            }
            state[inst] = entry
        self.state_mgr.save_state(region, state)

    def list_failed(self, region):
        state = self.state_mgr.load_state(region)
        failed = {k: v for k, v in state.items() if v["Status"] == "FAILED"}
        print(json.dumps(failed, indent=2))

    def list_unmanaged(self, region):
        ec2_resource = self.session.resource("ec2", region_name=region)
        ssm_client = self.session.client("ssm", region_name=region)
        all_instances = set(self.get_all_instances(ec2_resource))
        ssm_instances = set(self.get_ssm_managed(ssm_client))
        unmanaged = list(all_instances - ssm_instances)
        print(json.dumps(unmanaged, indent=2))

    def ssm_bulk(self, region, count=None, percent=None):
        ec2_resource = self.session.resource("ec2", region_name=region)
        ssm_client = self.session.client("ssm", region_name=region)
        lock_key = self.lock_mgr.acquire_lock(region)
        try:
            all_instances = set(self.get_all_instances(ec2_resource))
            ssm_instances = set(self.get_ssm_managed(ssm_client))
            state = self.state_mgr.load_state(region)
            pending_gen = (i for i in ssm_instances if i not in state)
            if percent:
                num = max(1, int(sum(1 for _ in pending_gen) * percent / 100))
                pending_gen = (i for i in ssm_instances if i not in state)
            elif count:
                num = min(count, sum(1 for _ in pending_gen))
                pending_gen = (i for i in ssm_instances if i not in state)
            else:
                logger.error("Must specify --count or --percent")
                return
            target = list(islice(pending_gen, num))
            logger.info(f"About to run on {len(target)} instances in {region}")
            confirm = input("Continue? (yes/no): ")
            if confirm.lower() != "yes":
                logger.info("Aborted by user")
                return
            self.run_ssm_on_instances(region, target)
        finally:
            self.lock_mgr.release_lock(lock_key)
            self.state_mgr.upload_log(region)

# ====================================================
# ---- CLI Commands ----
# ====================================================
@click.group()
def cli():
    """CLI tool for agent deployment in production (OOP)"""
    pass

@cli.command()
@click.option("--profile", required=True, help="AWS profile to use")
@click.option("--bucket", required=True, help="S3 bucket for state and logs")
def report(profile, bucket):
    """Generate deployment report for all regions with EC2 instances"""
    mgr = AWSAgentManager(profile, bucket)
    logger.info(f"Profile={profile}")
    reports = mgr.generate_report_all_regions()
    mgr.print_report_table(reports)
    logger.info(json.dumps(reports, indent=2))
    if reports:
        mgr.state_mgr.upload_log(reports[0]["region"])

@cli.command()
@click.option("--profile", required=True)
@click.option("--bucket", required=True)
@click.option("--region", required=True)
@click.option("--count", default=None, type=int, help="Number of instances to run on")
@click.option("--percent", default=None, type=int, help="Percentage of instances to run on")
def ssm(profile, bucket, region, count, percent):
    """Run SSM agent install on pending instances"""
    mgr = AWSAgentManager(profile, bucket, region)
    mgr.ssm_bulk(region, count, percent)

@cli.command()
@click.option("--profile", required=True)
@click.option("--bucket", required=True)
@click.option("--region", required=True)
def failed(profile, bucket, region):
    """List failed instances"""
    mgr = AWSAgentManager(profile, bucket, region)
    mgr.list_failed(region)

@cli.command()
@click.option("--profile", required=True)
@click.option("--bucket", required=True)
@click.option("--region", required=True)
def unmanaged(profile, bucket, region):
    """List unmanaged instances (any state, not in SSM)"""
    mgr = AWSAgentManager(profile, bucket, region)
    mgr.list_unmanaged(region)

# ====================================================
# ---- Main Entrypoint ----
# ====================================================
if __name__ == "__main__":
    cli()