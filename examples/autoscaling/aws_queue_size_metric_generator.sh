#!/bin/bash

# Runs on CR-master (can run on any other machine with access to AWS and CR-master).
# This script reports ClusterRunner master's build queue size to AWS cloudwatch.
# Install this script as a cronjob with following crontab entry
# * * * * * /home/jenkins/aws_queue_size_metric_generator.sh
# Note that this script will not run as it is as it will need updates with appropriate
# paths / URLs / credentials etc. In future these configuration details can be
# provided through config file.

CR_MASTER_URL="<ClusterRunner master URL>:<port>"
PATH_TO_VENV="<venv path>"
MASTER_INSTANCE_ID="<EC2 instance id for CR-master>"

# Grab queue size from CR master
Q_SIZE=$(curl https://$CR_MASTER_URL/v1/queue | jq '.queue | .[] | .status' | grep QUEUED | wc -l)
source $PATH_TO_VENV/activate
# Report queue size to cloudwatch
aws cloudwatch put-metric-data --metric-name QueueSize --namespace ss-autoscaling-test --unit Count --dimensions
        InstanceId=$MASTER_INSTANCE_ID --value $Q_SIZE
deactivate

