"""
CloudWise Deployment Services Package

The deployment pipeline targets AWS EC2 inside the *user's* AWS account
(assumed via STS with a per-user external id). There is exactly one
active provider implementation; there is no mock or simulated provider
in the production path.
"""

from .provider import DeploymentProvider
from .status import DeploymentStatus, DeploymentStage, is_valid_transition
from .log_service import DeploymentLogService, make_log_entry
from .aws_connection_service import AwsConnectionError
from .aws_ec2_provider import AwsEc2Provider, AwsEc2Error
from .pipeline import start_pipeline, run_pipeline

__all__ = [
    "DeploymentProvider",
    "DeploymentStatus",
    "DeploymentStage",
    "is_valid_transition",
    "DeploymentLogService",
    "make_log_entry",
    "AwsConnectionError",
    "AwsEc2Provider",
    "AwsEc2Error",
    "start_pipeline",
    "run_pipeline",
]
