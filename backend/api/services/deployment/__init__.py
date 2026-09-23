"""
CloudWise Deployment Services Package

Provider-independent mock deployment architecture.
Supports future cloud provider integration without AWS dependency.
"""

from .provider import DeploymentProvider
from .mock_provider import MockDeploymentProvider
from .status import DeploymentStatus, DeploymentStage, is_valid_transition
from .log_service import DeploymentLogService, make_log_entry
from .health_check import DeploymentHealthCheckService
from .rollback import DeploymentRollbackService
from .aws_connection_service import AwsConnectionError
from .aws_ec2_provider import AwsEc2Provider, AwsEc2Error

__all__ = [
    "DeploymentProvider",
    "MockDeploymentProvider",
    "DeploymentStatus",
    "DeploymentStage",
    "is_valid_transition",
    "DeploymentLogService",
    "make_log_entry",
    "DeploymentHealthCheckService",
    "DeploymentRollbackService",
    "AwsConnectionError",
    "AwsEc2Provider",
    "AwsEc2Error",
]
