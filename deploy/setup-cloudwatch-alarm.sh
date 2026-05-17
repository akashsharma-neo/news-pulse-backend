#!/usr/bin/env bash
# Create a simple EC2 CPU high alarm (requires instance ID).
# Usage: INSTANCE_ID=i-xxx SNS_TOPIC_ARN=arn:aws:sns:... ./deploy/setup-cloudwatch-alarm.sh
set -euo pipefail

AWS_REGION="${AWS_REGION:-ap-south-1}"
INSTANCE_ID="${INSTANCE_ID:?set INSTANCE_ID}"
SNS_TOPIC_ARN="${SNS_TOPIC_ARN:-}"
ALARM_NAME="${ALARM_NAME:-newspulse-ec2-cpu-high}"

ARGS=(
	--alarm-name "$ALARM_NAME"
	--alarm-description "NewsPulse EC2 CPU > 80% for 15 minutes"
	--metric-name CPUUtilization
	--namespace AWS/EC2
	--statistic Average
	--period 300
	--threshold 80
	--comparison-operator GreaterThanThreshold
	--evaluation-periods 3
	--dimensions "Name=InstanceId,Value=${INSTANCE_ID}"
	--region "$AWS_REGION"
)
if [[ -n "$SNS_TOPIC_ARN" ]]; then
	ARGS+=(--alarm-actions "$SNS_TOPIC_ARN")
fi

aws cloudwatch put-metric-alarm "${ARGS[@]}"
echo "CloudWatch alarm ${ALARM_NAME} created for ${INSTANCE_ID}"
