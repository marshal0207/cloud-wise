"""
Canonical AWS IAM policy generator for CloudWise.

This module exposes ONE source of truth for the trust and permissions
policies that a user must paste into their IAM role.

Do NOT maintain different hardcoded policies in different places.
The frontend receives the policy from the backend API via get_cloudwise_*()
functions. The backend also uses these same policies for the permission
preflight check (Part 22).

Exported symbols
----------------
get_cloudwise_trust_policy(external_id) -> dict
get_cloudwise_permissions_policy() -> list[dict]
get_cloudwise_permissions_policy_document() -> dict
get_required_permissions() -> list[dict]
"""

import uuid


CLOUDWISE_PERMISSIONS_POLICY_NAME = "CloudWiseDeployPolicy"
CLOUDWISE_TRUSTED_ACCOUNT_ID = "038658707850"


def generate_external_id(user_id: str) -> str:
    """
    Generate a unique cryptographically random External ID per user connection.

    Format: cloudwise-{user_id}-{uuid_hex_16}
    Protects against the confused-deputy problem.
    """
    return f"cloudwise-{user_id}-{uuid.uuid4().hex[:16]}"


def get_cloudwise_trust_policy(
    external_id: str,
    account_id: str | None = None,
) -> dict:
    """
    Return the trust policy document that allows CloudWise to assume a role
    via STS AssumeRole, restricted to the per-user External ID.
    """
    trusted = account_id or CLOUDWISE_TRUSTED_ACCOUNT_ID

    return {
        "Version": "2012-10-17",
        "Statement": [
            {
                "Sid": "CloudWiseAssumeRoleWithExternalId",
                "Effect": "Allow",
                "Principal": {
                    "AWS": f"arn:aws:iam::{trusted}:root"
                },
                "Action": "sts:AssumeRole",
                "Condition": {
                    "StringEquals": {
                        "sts:ExternalId": external_id
                    }
                },
            }
        ],
    }


def get_cloudwise_permissions_policy() -> list[dict]:
    """
    Return the canonical Statement list.

    IMPORTANT:
    Keep this return type as list[dict] because the permission preflight
    consumes each statement/action from this function.

    The UI/API should wrap this list in a complete IAM policy document
    using get_cloudwise_permissions_policy_document().
    """
    return [
        {
            "Sid": "CloudWiseEC2Describe",
            "Effect": "Allow",
            "Action": [
                "ec2:DescribeInstances",
                "ec2:DescribeInstanceStatus",
                "ec2:DescribeImages",
                "ec2:DescribeSecurityGroups",
                "ec2:DescribeVpcs",
                "ec2:DescribeSubnets",
                "ec2:DescribeAvailabilityZones",
                "ec2:DescribeKeyPairs",
                "ec2:DescribeTags",
                "ec2:DescribeVolumes",
                "ec2:DescribeIamInstanceProfileAssociations",
            ],
            "Resource": "*",
        },
        {
            "Sid": "CloudWiseElasticIp",
            "Effect": "Allow",
            # Optional capability: keeps the instance public IP stable
            # across rebuilds so a database network access list keeps
            # matching. Without these the pipeline still deploys, using
            # the instance's dynamic public IP.
            "Action": [
                "ec2:DescribeAddresses",
                "ec2:AllocateAddress",
                "ec2:AssociateAddress",
                "ec2:DisassociateAddress",
                "ec2:ReleaseAddress",
            ],
            "Resource": "*",
        },
        {
            "Sid": "CloudWiseEC2Lifecycle",
            "Effect": "Allow",
            "Action": [
                "ec2:RunInstances",
                "ec2:StartInstances",
                "ec2:StopInstances",
                "ec2:RebootInstances",
                "ec2:TerminateInstances",
                "ec2:CreateTags",
                "ec2:ModifyInstanceAttribute",
            ],
            "Resource": "*",
        },
        {
            "Sid": "CloudWiseSecurityGroupConfig",
            "Effect": "Allow",
            "Action": [
                "ec2:CreateSecurityGroup",
                "ec2:AuthorizeSecurityGroupIngress",
                "ec2:AuthorizeSecurityGroupEgress",
                "ec2:RevokeSecurityGroupIngress",
                "ec2:RevokeSecurityGroupEgress",
            ],
            "Resource": "*",
        },
        {
            "Sid": "CloudWisePassInstanceRole",
            "Effect": "Allow",
            "Action": "iam:PassRole",
            "Resource": "arn:aws:iam::*:role/cloudwise-ec2-*",
            "Condition": {
                "StringEquals": {
                    "iam:PassedToService": "ec2.amazonaws.com"
                }
            },
        },
        {
            "Sid": "CloudWiseReadPublicAmiParameter",
            "Effect": "Allow",
            "Action": [
                "ssm:GetParameter",
                "ssm:GetParameters",
            ],
            # FIX:
            # The previous ARN was malformed for an SSM parameter and caused
            # AWS to return AccessDenied for ssm:GetParameter.
            "Resource": "*",
        },
        {
            "Sid": "CloudWiseSsmContainerDeploy",
            "Effect": "Allow",
            "Action": [
                "ssm:SendCommand",
                "ssm:GetCommandInvocation",
                "ssm:ListCommands",
                "ssm:DescribeInstanceInformation",
                "ssm:DescribeInstanceAssociations",
            ],
            "Resource": "*",
        },
        {
            "Sid": "CloudWiseTagging",
            "Effect": "Allow",
            "Action": [
                "ec2:CreateTags",
            ],
            "Resource": "*",
        },
    ]


def get_cloudwise_permissions_policy_document() -> dict:
    """
    Return a complete IAM policy document suitable for:

    AWS Console -> IAM -> Policies -> Create policy -> JSON

    The preflight still consumes get_cloudwise_permissions_policy().
    """
    return {
        "Version": "2012-10-17",
        "Statement": get_cloudwise_permissions_policy(),
    }


def get_required_permissions() -> list[dict]:
    """
    Alias for get_cloudwise_permissions_policy().

    Kept for semantic clarity in the permission preflight (Part 22).
    """
    return get_cloudwise_permissions_policy()
