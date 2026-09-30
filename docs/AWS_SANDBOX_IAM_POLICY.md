# AWS Sandbox Account & Least-Privilege IAM Policy Guide

This document defines the IAM security policy, Free Tier guardrails, and setup procedure for the CloudWise team AWS sandbox account.

---

## 1. Overview & Security Principles

CloudWise interacts with AWS in two distinct ways:
1. **Pricing Service (`aws_pricing_service.py`)**: Read-only queries to the AWS Price List Service API to fetch live hourly compute rates.
2. **Deployment Pipeline (`deployment_file_generator.py`)**: GitHub Actions CI/CD workflows that authenticate via AWS credentials, build Docker container images, push them to Amazon ECR, and deploy to containerized hosts.

### Free Tier Alignment (`free_tier_policy.py`)
The IAM policy strictly mirrors the limits defined in [`backend/api/services/free_tier_policy.py`](file:///d:/5th_Sem/SGP/CloudWise/backend/api/services/free_tier_policy.py):

| Resource | `free_tier_policy.py` Enforcement | IAM Policy Enforcement (`Condition`) |
| :--- | :--- | :--- |
| **Instance Type** | `t2.micro`, `t3.micro` (or `t3.small`) | `"ec2:InstanceType": ["t2.micro", "t3.micro", "t3.small"]` |
| **vCPU Limit** | Max 2 vCPUs | Enforced by instance type restriction (t3.small is max 2 vCPUs) |
| **RAM Limit** | Max 2 GB RAM | Enforced by instance type restriction (t3.small is max 2 GB) |
| **EBS Storage** | Max 30 GB EBS | `"NumericLessThanEquals": { "ec2:VolumeSize": "30" }` |
| **Regions** | Mumbai (`ap-south-1`), Global Pricing (`us-east-1`) | `"StringEquals": { "aws:RequestedRegion": ["ap-south-1", "us-east-1"] }` |
| **ECR Repositories** | Scoped to project apps | Scoped to `arn:aws:ecr:*:*:repository/cloudwise-*` |

---

## 2. Complete IAM Policy (JSON)

Attach this policy (`CloudWiseSandboxDeployerPolicy`) to the dedicated IAM User or IAM Role used by the team / GitHub Actions:

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "AllowPricingApiReadOnly",
      "Effect": "Allow",
      "Action": [
        "pricing:DescribeServices",
        "pricing:GetProducts",
        "pricing:GetAttributeValues"
      ],
      "Resource": "*"
    },
    {
      "Sid": "AllowECRAuthToken",
      "Effect": "Allow",
      "Action": [
        "ecr:GetAuthorizationToken"
      ],
      "Resource": "*"
    },
    {
      "Sid": "AllowECRPushAndPullCloudWiseOnly",
      "Effect": "Allow",
      "Action": [
        "ecr:BatchCheckLayerAvailability",
        "ecr:GetDownloadUrlForLayer",
        "ecr:BatchGetImage",
        "ecr:PutImage",
        "ecr:InitiateLayerUpload",
        "ecr:UploadLayerPart",
        "ecr:CompleteLayerUpload",
        "ecr:DescribeRepositories",
        "ecr:CreateRepository"
      ],
      "Resource": [
        "arn:aws:ecr:*:*:repository/cloudwise-*"
      ]
    },
    {
      "Sid": "AllowEC2ReadOperations",
      "Effect": "Allow",
      "Action": [
        "ec2:DescribeInstances",
        "ec2:DescribeImages",
        "ec2:DescribeInstanceStatus",
        "ec2:DescribeSecurityGroups",
        "ec2:DescribeSubnets",
        "ec2:DescribeVpcs",
        "ec2:DescribeKeyPairs"
      ],
      "Resource": "*"
    },
    {
      "Sid": "AllowRestrictedEC2RunInstancesFreeTierOnly",
      "Effect": "Allow",
      "Action": [
        "ec2:RunInstances"
      ],
      "Resource": [
        "arn:aws:ec2:*:*:instance/*"
      ],
      "Condition": {
        "StringEquals": {
          "ec2:InstanceType": [
            "t2.micro",
            "t3.micro",
            "t3.small"
          ]
        }
      }
    },
    {
      "Sid": "AllowRestrictedEBSVolumesFreeTierOnly",
      "Effect": "Allow",
      "Action": [
        "ec2:RunInstances"
      ],
      "Resource": [
        "arn:aws:ec2:*:*:volume/*"
      ],
      "Condition": {
        "NumericLessThanEquals": {
          "ec2:VolumeSize": "30"
        }
      }
    },
    {
      "Sid": "AllowEC2SupportingResourcesForRunInstances",
      "Effect": "Allow",
      "Action": [
        "ec2:RunInstances"
      ],
      "Resource": [
        "arn:aws:ec2:*:*:image/*",
        "arn:aws:ec2:*:*:security-group/*",
        "arn:aws:ec2:*:*:subnet/*",
        "arn:aws:ec2:*:*:network-interface/*",
        "arn:aws:ec2:*:*:key-pair/*"
      ]
    },
    {
      "Sid": "AllowManageCloudWiseInstancesOnly",
      "Effect": "Allow",
      "Action": [
        "ec2:StartInstances",
        "ec2:StopInstances",
        "ec2:TerminateInstances",
        "ec2:RebootInstances"
      ],
      "Resource": "arn:aws:ec2:*:*:instance/*",
      "Condition": {
        "StringEquals": {
          "ec2:ResourceTag/Project": "CloudWise"
        }
      }
    }
  ]
}
```

---

## 3. Step-by-Step AWS Setup Instructions

### Step 1: Create IAM Group & User
1. Log in to the AWS Console as an Administrator.
2. Go to **IAM → Policies → Create Policy**.
3. Choose the **JSON** tab and paste the complete policy JSON from Section 2 above.
4. Name the policy: `CloudWiseSandboxDeployerPolicy`.
5. Go to **IAM → Users → Create User**:
   - Username: `cloudwise-team-sandbox`
   - Access type: Programmatic access (Access key - CLI, SDK, and third-party tools).
6. Attach `CloudWiseSandboxDeployerPolicy` directly or via a group.
7. Save the generated `AWS_ACCESS_KEY_ID` and `AWS_SECRET_ACCESS_KEY`.

### Step 2: Configure AWS Budgets ($0 & $5 Alarms)
To guarantee zero unexpected charges:
1. Go to **AWS Billing and Cost Management → Budgets → Create Budget**.
2. Select **Cost Budget** (monthly):
   - Budget Amount: `$5.00`
   - Threshold 1: Alert at `80%` ($4.00) to team emails.
   - Threshold 2: Alert at `100%` ($5.00) to team emails.
3. Select **Zero Spend Budget** / **Free Tier Usage Alerts**:
   - Turn on **Receive Free Tier Usage Alerts** to be notified before exceeding 750 free t2/t3.micro hours or 30 GB EBS.

### Step 3: Configure Environment & GitHub Secrets
1. **Local Developer Setup (`backend/.env`)**:
   ```bash
   AWS_ACCESS_KEY_ID=AKIA...
   AWS_SECRET_ACCESS_KEY=...
   AWS_REGION=ap-south-1
   AWS_PRICING_API_REGION=us-east-1
   ```
2. **GitHub Actions Secrets** (in repository settings):
   - `AWS_ACCESS_KEY_ID`: `cloudwise-team-sandbox` Access Key
   - `AWS_SECRET_ACCESS_KEY`: `cloudwise-team-sandbox` Secret Key
   - `AWS_REGION`: `ap-south-1`

---

## 4. Verification Check

To test this policy locally using the AWS CLI:
```bash
# 1. Test Price List API access
aws pricing describe-services --service-code AmazonEC2 --region us-east-1

# 2. Test ECR authorization token
aws ecr get-login-password --region ap-south-1

# 3. Test EC2 Free Tier guardrail (should fail if instance type is not t2/t3.micro/small or EBS > 30GB)
aws ec2 run-instances --image-id ami-00bb6a80f01f03502 --instance-type c6i.xlarge --region ap-south-1
# Returns: Client.UnauthorizedOperation (AccessDenied by IAM Policy)
```
