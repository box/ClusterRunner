#!/bin/bash

# Runs on CR-master (can run on any other machine with access to AWS and CR-master).
# This script monitors the AWS-SQS to grab the instance ids of terminating instances
# (as a part of scale-in) and converts them into CR slave ids. It shutdowns these
# instances and clears the processed messages from SQS. If the instances are monitored
# (e.g. by Nogios), then we have to add a step to decommission the instance.
# Install this script as a cronjob with following crontab entry
# 5 * * * * /<path>/aws_autoscaling_queue_handler.sh >> /home/jenkins/qhandler.log
# Note that this script will not run as it is as it will need updates with appropriate
# paths / URLs / credentials etc. In future these configuration details can be
# provided through config file.


set -e
set -o pipefail

SQS_QUERY_URL="<URL to AWS Simple Queue Service>"
CR_MASTER_URL="<ClusterRunner master URL>:<port>"
CR_CONFIG_FILE="<path to ClusterRunner config file>"
DOMAIN_NAME="<domain name>"
CR_SLAVE_PORT="43001"
SQS_VISIBILITY_TIMEOUT=300
PATH_TO_VENV="<venv path>"


# Enable the python virtual env, this env has AWS credentials configured
source $PATH_TO_VENV/activate

# SQS stores messages in distributed enviroment so query multiple times
for i in {1..5}
do
        # Get queued messages
        Q_MSGS=$(aws sqs receive-message --queue-url $SQS_QUERY_URL --wait-time-seconds 20 --max-number-of-messages 10
                --visibility-timeout $SQS_VISIBILITY_TIMEOUT)
        # Parse messages
        Q_MSGS_PARSED=$(echo $Q_MSGS | jq '.Messages | .[] | select (.Body | fromjson.LifecycleTransition != null) |
                select (.Body | fromjson.LifecycleTransition | contains("autoscaling:EC2_INSTANCE_TERMINATING")) |
                {MessageId: .MessageId, ReceiptHandle: .ReceiptHandle, InstanceId: .Body | fromjson.EC2InstanceId}')

        # Retrieve IP address for the instances which will be terminated as part of scale-in
        INSTANCE_IDS=$(echo $Q_MSGS_PARSED | jq '.InstanceId' | tr -d '"' | tr '\n' ' ')
        echo "$(date): AWS-SQS-Q-Handler: Instance terminate is called for instances - $INSTANCE_IDS."
        if [ -z "$INSTANCE_IDS" ]
        then
                echo "$(date): AWS-SQS-Q-Handler: Could not find any valid Instance IDs marked for termination."
                echo "$(date): AWS-SQS-Q-Handler: Skipping step to shutdown and remove slaves from CR master."
        else
                INSTANCE_IPS=$(aws ec2 describe-instances --instance-ids $INSTANCE_IDS --query
                        'Reservations[*].Instances[*].PrivateIpAddress' | jq '.[] | .[]')
                echo "$(date): AWS-SQS-Q-Handler: Instance terminate is called for instances with IP addresses - $INSTANCE_IPS."

                # Get list of slave ids from CR-master and call shutdown endpoint for all slave ids
                if [ -z "$INSTANCE_IPS" ]
                then
                        echo "$(date): AWS-SQS-Q-Handler: Could not find any IP address (instances must not be running)."
                        echo "$(date): AWS-SQS-Q-Handler: Skipping step to shutdown and remove slaves from CR master."
                else
                        hn_url_list=""
                        for ip in $INSTANCE_IPS
                        do
                                hn_url="ip-"$(echo $ip | tr . - | tr -d '"')"."$DOMAIN_NAME":"$CR_SLAVE_PORT
                                if [ -z "$hn_url_list" ]
                                then
                                        hn_url_list+='"'$hn_url'"'
                                else
                                        hn_url_list+=',"'$hn_url'"'
                                fi
                        done
                        JQ_CMD=".slaves | .[] | select (.url as \$a | ["$hn_url_list"] | index(\$a)) | .id"
                        CR_SLAVE_IDS=$(curl $CR_MASTER_URL/v1/slave | jq "$JQ_CMD")
                        echo "$(date): AWS-SQS-Q-Handler: Calling CR-master $CR_MASTER_URL to shutdown slaves $CR_SLAVE_IDS."
                        python cr_shutdown_slaves.py $CR_MASTER_URL $CR_CONFIG_FILE $CR_SLAVE_IDS
                fi
        fi

        # Delete received messages from SQS
        RECEIPT_HANDLES=$(echo $Q_MSGS_PARSED | jq '.ReceiptHandle' | tr -d '"')
        for rh in $RECEIPT_HANDLES
        do
                echo "$(date): AWS-SQS-Q-Handler: Deleting SQS message $rh"
                aws sqs delete-message --queue-url $SQS_QUERY_URL --receipt-handle $rh
        done

done

# Deactivate the python virtual env
deactivate
