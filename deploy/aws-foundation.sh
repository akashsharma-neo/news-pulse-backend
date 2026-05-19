#!/usr/bin/env bash
# Create ECR repos, security group, EC2 key pair hint, IAM role/policy, Elastic IP.
# Requires: AWS CLI, credentials with EC2/ECR/IAM permissions.
#
# Usage:
#   export AWS_REGION=ap-south-1
#   export PROJECT=newspulse
#   ./deploy/aws-foundation.sh
#
# Optional: KEY_NAME=my-key (existing EC2 key pair for SSH)
set -euo pipefail

if ! command -v aws &>/dev/null; then
	echo "AWS CLI not found. Install it, then re-run:" >&2
	echo "  macOS:  brew install awscli" >&2
	echo "  Linux:  see deploy/bootstrap-ec2.sh (installs on EC2)" >&2
	echo "  Docs:   https://docs.aws.amazon.com/cli/latest/userguide/getting-started-install.html" >&2
	exit 1
fi

AWS_REGION="${AWS_REGION:-ap-south-1}"
PROJECT="${PROJECT:-newspulse}"
INSTANCE_TYPE="${INSTANCE_TYPE:-t4g.small}"
VOLUME_GB="${VOLUME_GB:-40}"
KEY_NAME="${KEY_NAME:-}"

echo "Region: ${AWS_REGION}  Project: ${PROJECT}"

ACCOUNT_ID="$(aws sts get-caller-identity --query Account --output text)"
echo "Account: ${ACCOUNT_ID}"

for repo in newspulse-api newspulse-api-embeddings newspulse-web; do
	if aws ecr describe-repositories --repository-names "$repo" --region "$AWS_REGION" &>/dev/null; then
		echo "ECR repo exists: ${repo}"
	else
		aws ecr create-repository --repository-name "$repo" --region "$AWS_REGION" \
			--image-scanning-configuration scanOnPush=true
		echo "Created ECR repo: ${repo}"
	fi
done

VPC_ID="$(aws ec2 describe-vpcs --filters Name=isDefault,Values=true --query 'Vpcs[0].VpcId' --output text --region "$AWS_REGION")"
SUBNET_ID="$(aws ec2 describe-subnets --filters Name=vpc-id,Values="$VPC_ID" Name=default-for-az,Values=true \
	--query 'Subnets[0].SubnetId' --output text --region "$AWS_REGION")"
echo "VPC: ${VPC_ID}  Subnet: ${SUBNET_ID}"

SG_NAME="${PROJECT}-prod-sg"
SG_ID="$(aws ec2 describe-security-groups --filters "Name=group-name,Values=${SG_NAME}" \
	--query 'SecurityGroups[0].GroupId' --output text --region "$AWS_REGION" 2>/dev/null || echo "None")"
if [[ "$SG_ID" == "None" || -z "$SG_ID" ]]; then
	SG_ID="$(aws ec2 create-security-group --group-name "$SG_NAME" \
		--description "NewsPulse production" --vpc-id "$VPC_ID" --region "$AWS_REGION" \
		--query GroupId --output text)"
	# HTTP/HTTPS public; SSH optional (restrict to your IP in console)
	aws ec2 authorize-security-group-ingress --group-id "$SG_ID" --region "$AWS_REGION" \
		--ip-permissions \
		IpProtocol=tcp,FromPort=80,ToPort=80,IpRanges='[{CidrIp=0.0.0.0/0}]' \
		IpProtocol=tcp,FromPort=443,ToPort=443,IpRanges='[{CidrIp=0.0.0.0/0}]'
	echo "Created security group: ${SG_ID} — add SSH (22) from your IP if needed"
else
	echo "Security group exists: ${SG_ID}"
fi

ROLE_NAME="${PROJECT}-ec2-ecr-role"
INSTANCE_PROFILE="${PROJECT}-ec2-ecr-profile"

if ! aws iam get-role --role-name "$ROLE_NAME" &>/dev/null; then
	aws iam create-role --role-name "$ROLE_NAME" --assume-role-policy-document '{
	  "Version": "2012-10-17",
	  "Statement": [{
	    "Effect": "Allow",
	    "Principal": {"Service": "ec2.amazonaws.com"},
	    "Action": "sts:AssumeRole"
	  }]
	}'
	aws iam attach-role-policy --role-name "$ROLE_NAME" \
		--policy-arn arn:aws:iam::aws:policy/AmazonSSMManagedInstanceCore
	aws iam put-role-policy --role-name "$ROLE_NAME" --policy-name ecr-pull \
		--policy-document "{
	  \"Version\": \"2012-10-17\",
	  \"Statement\": [{
	    \"Effect\": \"Allow\",
	    \"Action\": [
	      \"ecr:GetAuthorizationToken\",
	      \"ecr:BatchCheckLayerAvailability\",
	      \"ecr:GetDownloadUrlForLayer\",
	      \"ecr:BatchGetImage\"
	    ],
	    \"Resource\": \"*\"
	  }]
	}"
	echo "Created IAM role: ${ROLE_NAME}"
fi

if ! aws iam get-instance-profile --instance-profile-name "$INSTANCE_PROFILE" &>/dev/null; then
	aws iam create-instance-profile --instance-profile-name "$INSTANCE_PROFILE"
	aws iam add-role-to-instance-profile --instance-profile-name "$INSTANCE_PROFILE" --role-name "$ROLE_NAME"
	echo "Created instance profile: ${INSTANCE_PROFILE}"
fi

AMI_ID="$(aws ssm get-parameters --names /aws/service/ami-amazon-linux-latest/al2023-ami-kernel-6.1-arm64 \
	--region "$AWS_REGION" --query 'Parameters[0].Value' --output text)"

echo ""
echo "Launch EC2 (adjust KEY_NAME or omit for SSM-only):"
LAUNCH_ARGS=(
	--image-id "$AMI_ID"
	--instance-type "$INSTANCE_TYPE"
	--subnet-id "$SUBNET_ID"
	--security-group-ids "$SG_ID"
	--iam-instance-profile "Name=${INSTANCE_PROFILE}"
	--block-device-mappings "[{\"DeviceName\":\"/dev/xvda\",\"Ebs\":{\"VolumeSize\":${VOLUME_GB},\"VolumeType\":\"gp3\",\"DeleteOnTermination\":true}}]"
	--tag-specifications "ResourceType=instance,Tags=[{Key=Name,Value=${PROJECT}-prod}]"
	--region "$AWS_REGION"
)
if [[ -n "$KEY_NAME" ]]; then
	LAUNCH_ARGS+=(--key-name "$KEY_NAME")
fi

echo "  aws ec2 run-instances ${LAUNCH_ARGS[*]}"
echo ""
echo "Then allocate and associate an Elastic IP:"
echo "  ALLOC=\$(aws ec2 allocate-address --domain vpc --region ${AWS_REGION} --query AllocationId --output text)"
echo "  aws ec2 associate-address --instance-id <i-xxx> --allocation-id \$ALLOC --region ${AWS_REGION}"
echo ""
echo "ECR images:"
echo "  ${ACCOUNT_ID}.dkr.ecr.${AWS_REGION}.amazonaws.com/newspulse-api:latest"
echo "  ${ACCOUNT_ID}.dkr.ecr.${AWS_REGION}.amazonaws.com/newspulse-web:latest"
