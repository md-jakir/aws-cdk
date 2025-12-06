#!/usr/bin/env python3
import os
import json
import sys

import aws_cdk as cdk

from hello_ecs.hello_ecs_stack import DemoEcsStack


app = cdk.App()

# Get environment from context or default to 'dev'
environment = app.node.try_get_context("environment") or "dev"

# Load environment configuration
config_file = os.path.join(os.path.dirname(__file__), "config.json")
with open(config_file, 'r') as f:
    config = json.load(f)

if environment not in config:
    raise ValueError(f"Environment '{environment}' not found in config.json. Available: {list(config.keys())}")

env_config = config[environment]

# Path to task definition JSON files
taskdef_file = os.path.join(os.path.dirname(__file__), "taskdef.json")
chatbot_frontend_taskdef_file = os.path.join(os.path.dirname(__file__), "chatbot-frontend.json")

# Create stack with environment-specific configuration
DemoEcsStack(app, f"DemoEcsStack-{environment}",
    taskdef_path=taskdef_file,
    chatbot_frontend_taskdef_path=chatbot_frontend_taskdef_file,
    environment=environment,
    config=env_config,
    # Uncomment to specify AWS account/region:
    # env=cdk.Environment(account=os.getenv('CDK_DEFAULT_ACCOUNT'), region=os.getenv('CDK_DEFAULT_REGION')),
)

app.synth()