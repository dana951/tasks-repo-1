provider "aws" {
  region = "us-east-1"
  assume_role {
    role_arn = "arn:aws:iam::<test-account-id>:role/TEST-AGENT-Role"
  }
}

resource "aws_instance" "test_agent" {
  ami           = var.ami_id
  instance_type = "t3.micro"
  key_name      = var.key_name

  user_data = <<-EOF
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
              EOF

  tags = {
    Name = "test-agent-instance"
  }
}

variable "ami_id" {
  description = "AMI ID for the test instance"
  type        = string
}

variable "key_name" {
  description = "SSH key name"
  type        = string
}