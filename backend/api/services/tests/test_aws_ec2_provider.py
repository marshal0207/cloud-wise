"""
Tests for AwsEc2Provider (Part 3 — EC2 provisioning only).

Covers: DeploymentProvider interface, state-machine progression,
create vs reuse of CloudWise-managed EC2, security-group ports
(80/443/22 only), Docker user data, status/health/rollback, deferred
container deploy, and that no credentials leak into logs/returns.
"""

from unittest.mock import MagicMock, patch

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings

from api.models import AWSConnection, EC2Instance
from api.services.deployment.aws_ec2_provider import AwsEc2Error, AwsEc2Provider
from api.services.deployment.provider import DeploymentProvider
from api.services.deployment.status import DeploymentStatus

User = get_user_model()


def _make_instance(instance_id="i-0abc123", state="running", ip="13.232.1.10"):
    return {
        "InstanceId": instance_id,
        "State": {"Name": state},
        "PublicIpAddress": ip if state == "running" else "",
        "PrivateIpAddress": "10.0.0.10",
        "InstanceType": "t3.micro",
        "ImageId": "ami-0abc123",
    }


def _make_mocks(instance=None, ami="ami-0abc123"):
    """Build a coherent set of EC2/SSM client mocks for the happy path."""
    instance = instance or _make_instance()
    ec2 = MagicMock()
    ec2.describe_vpcs.return_value = {"Vpcs": [{"VpcId": "vpc-1"}]}
    ec2.describe_security_groups.return_value = {
        "SecurityGroups": [
            {
                "GroupId": "sg-1",
                "GroupName": "cloudwise-sg",
                "IpPermissions": [],
            }
        ]
    }
    ec2.create_security_group.return_value = {"GroupId": "sg-new"}
    ec2.describe_images.return_value = {
        "Images": [
            {
                "ImageId": ami,
                "RootDeviceName": "/dev/xvda",
                "CreationDate": "2026-01-01T00:00:00.000Z",
            }
        ]
    }
    ec2.describe_instances.return_value = {
        "Reservations": [{"Instances": [instance]}]
    }
    ec2.run_instances.return_value = {"Instances": [instance]}
    waiter = MagicMock()
    ec2.get_waiter.return_value = waiter

    ssm = MagicMock()
    ssm.get_parameter.return_value = {"Parameter": {"Value": ami}}

    session = MagicMock()

    def client_factory(service, **kwargs):
        return ec2 if service == "ec2" else ssm

    session.client.side_effect = client_factory
    return session, ec2, ssm


class ProviderContractTests(TestCase):
    """The provider implements the existing DeploymentProvider interface."""

    def test_implements_deployment_provider(self):
        self.assertTrue(issubclass(AwsEc2Provider, DeploymentProvider))

    def test_provider_type_is_aws(self):
        self.assertEqual(AwsEc2Provider.PROVIDER_TYPE, "AWS")

    def test_implements_spec_operations(self):
        provider = AwsEc2Provider()
        for method in ("start", "get_status", "get_logs", "health_check",
                       "rollback", "provision", "deploy", "status", "logs"):
            self.assertTrue(callable(getattr(provider, method)), method)


class ProvisioningTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="ec2user", password="pass1234", email="ec2@example.com"
        )
        self.connection = AWSConnection.objects.create(
            user=self.user,
            role_arn="arn:aws:iam::999988887777:role/CloudWiseDeployRole",
            external_id="cloudwise-user-xyz",
            account_id="999988887777",
            region="ap-south-1",
            status="active",
        )

    def _provider(self, **config):
        return AwsEc2Provider(
            user=self.user, connection=self.connection, config=config
        )

    def test_start_requires_active_connection(self):
        provider = AwsEc2Provider(user=self.user, connection=None)
        with self.assertRaises(AwsEc2Error):
            provider.start({"environment_name": "prod", "provider": "AWS"})

        self.connection.status = "pending"
        self.connection.save()
        provider = AwsEc2Provider(
            user=self.user, connection=self.connection
        )
        with self.assertRaises(AwsEc2Error):
            provider.start({"environment_name": "prod", "provider": "AWS"})

    def test_start_rejects_foreign_provider_name(self):
        provider = self._provider()
        with self.assertRaises(AwsEc2Error):
            provider.start({"environment_name": "prod", "provider": "VERCEL"})

    @override_settings(AWS_INSTALL_DOCKER=True)
    def test_creates_new_ec2_instance(self):
        session, ec2, _ssm = _make_mocks()
        provider = self._provider()

        with patch.object(provider, "get_session", return_value=session):
            result = provider.start(
                {"environment_name": "prod", "provider": "AWS"}
            )

        self.assertEqual(result["status"], DeploymentStatus.RUNNING)
        self.assertEqual(result["provider_type"], "AWS")
        self.assertEqual(result["instance_id"], "i-0abc123")
        self.assertEqual(result["deployment_id"], "i-0abc123")
        self.assertFalse(result["reused"])
        self.assertEqual(result["public_ip"], "13.232.1.10")
        self.assertEqual(result["security_group_id"], "sg-1")
        self.assertTrue(result["docker_installed"])
        ec2.run_instances.assert_called_once()

        # Instance row persisted for reuse
        row = EC2Instance.objects.get(instance_id="i-0abc123")
        self.assertEqual(row.user_id, self.user.id)
        self.assertEqual(row.status, "running")
        self.assertTrue(row.docker_installed)
        self.assertEqual(row.deployment_count, 1)

        # State machine walked through all provisioning stages
        stages = [log["stage"] for log in result["logs"]]
        for expected in (
            "PREPARING",
            "BUILDING",
            "DEPLOYING",
            "HEALTH_CHECK",
            "COMPLETED",
        ):
            self.assertIn(expected, stages)

    @override_settings(AWS_INSTALL_DOCKER=True)
    def test_run_instances_receives_docker_user_data_and_tags(self):
        session, ec2, _ssm = _make_mocks()
        provider = self._provider()

        with patch.object(provider, "get_session", return_value=session):
            provider.start({"environment_name": "prod", "provider": "AWS"})

        kwargs = ec2.run_instances.call_args.kwargs
        user_data = kwargs.get("UserData", "")
        self.assertIn("docker", user_data)
        self.assertIn("docker-compose", user_data)
        # IMDSv2 enforced + ManagedBy tag for CloudWise ownership
        self.assertEqual(kwargs["MetadataOptions"]["HttpTokens"], "required")
        tag_dicts = kwargs["TagSpecifications"][0]["Tags"]
        tag_map = {t["Key"]: t["Value"] for t in tag_dicts}
        self.assertEqual(tag_map.get("ManagedBy"), "CloudWise")
        self.assertEqual(
            kwargs["SecurityGroupIds"], ["sg-1"]
        )
        self.assertNotIn("KeyName", kwargs)  # no SSH key configured by default

    @override_settings(AWS_INSTALL_DOCKER=False)
    def test_docker_install_can_be_disabled(self):
        session, ec2, _ssm = _make_mocks()
        provider = self._provider()

        with patch.object(provider, "get_session", return_value=session):
            result = provider.start(
                {"environment_name": "prod", "provider": "AWS"}
            )

        self.assertFalse(result["docker_installed"])
        kwargs = ec2.run_instances.call_args.kwargs
        self.assertNotIn("UserData", kwargs)

    def test_reuses_existing_cloudwise_managed_instance(self):
        EC2Instance.objects.create(
            user=self.user,
            instance_id="i-existing",
            region="ap-south-1",
            status="running",
        )
        existing = _make_instance(instance_id="i-existing")
        session, ec2, _ssm = _make_mocks(instance=existing)
        provider = self._provider()

        with patch.object(provider, "get_session", return_value=session):
            result = provider.start(
                {"environment_name": "prod", "provider": "AWS"}
            )

        self.assertTrue(result["reused"])
        self.assertEqual(result["instance_id"], "i-existing")
        ec2.run_instances.assert_not_called()

        row = EC2Instance.objects.get(instance_id="i-existing")
        self.assertEqual(row.deployment_count, 2)  # reuse increments counter

    def test_force_new_instance_skips_reuse(self):
        EC2Instance.objects.create(
            user=self.user,
            instance_id="i-existing",
            region="ap-south-1",
            status="running",
        )
        session, ec2, _ssm = _make_mocks()
        provider = self._provider()

        with patch.object(provider, "get_session", return_value=session):
            result = provider.start(
                {
                    "environment_name": "prod",
                    "provider": "AWS",
                    "force_new_instance": True,
                }
            )

        self.assertFalse(result["reused"])
        ec2.run_instances.assert_called_once()


class SecurityGroupTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="sguser", password="pass1234", email="sg@example.com"
        )
        self.connection = AWSConnection.objects.create(
            user=self.user,
            role_arn="arn:aws:iam::999988887777:role/CloudWiseDeployRole",
            external_id="cloudwise-sg",
            account_id="999988887777",
            region="ap-south-1",
            status="active",
        )

    @override_settings(AWS_SECURITY_GROUP_PORTS=[80, 443, 22])
    def test_opens_only_standard_ports(self):
        session, ec2, _ssm = _make_mocks()
        provider = AwsEc2Provider(
            user=self.user, connection=self.connection
        )

        with patch.object(provider, "get_session", return_value=session):
            provider.start({"environment_name": "prod", "provider": "AWS"})

        authorized_ports = sorted(
            call.kwargs.get("FromPort")
            for call in ec2.authorize_security_group_ingress.call_args_list
        )
        self.assertEqual(authorized_ports, [22, 80, 443])
        # Arbitrary application ports are never opened
        for app_port in (3000, 8000, 8080, 5432, 27017):
            self.assertNotIn(app_port, authorized_ports)

    @override_settings(AWS_SECURITY_GROUP_PORTS=[80, 443, 22])
    def test_creates_security_group_when_missing(self):
        session, ec2, _ssm = _make_mocks()
        ec2.describe_security_groups.return_value = {"SecurityGroups": []}
        provider = AwsEc2Provider(
            user=self.user, connection=self.connection
        )

        with patch.object(provider, "get_session", return_value=session):
            result = provider.start(
                {"environment_name": "prod", "provider": "AWS"}
            )

        ec2.create_security_group.assert_called_once()
        self.assertEqual(result["security_group_name"], "cloudwise-sg")
        self.assertEqual(result["security_group_id"], "sg-new")

    @override_settings(AWS_SECURITY_GROUP_PORTS=[80, 443, 22])
    def test_configurable_ports_from_settings(self):
        session, ec2, _ssm = _make_mocks()
        provider = AwsEc2Provider(
            user=self.user, connection=self.connection
        )
        with override_settings(AWS_SECURITY_GROUP_PORTS=[443, 22]):
            with patch.object(provider, "get_session", return_value=session):
                provider.start(
                    {"environment_name": "prod", "provider": "AWS"}
                )
        authorized_ports = sorted(
            call.kwargs.get("FromPort")
            for call in ec2.authorize_security_group_ingress.call_args_list
        )
        self.assertEqual(authorized_ports, [22, 443])


class StatusHealthRollbackTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="statuser", password="pass1234", email="stat@example.com"
        )
        self.connection = AWSConnection.objects.create(
            user=self.user,
            role_arn="arn:aws:iam::999988887777:role/CloudWiseDeployRole",
            external_id="cloudwise-status",
            account_id="999988887777",
            region="ap-south-1",
            status="active",
        )
        EC2Instance.objects.create(
            user=self.user,
            instance_id="i-live",
            region="ap-south-1",
            status="running",
            metadata={"logs": []},
        )

    def _provider(self, **config):
        return AwsEc2Provider(
            user=self.user, connection=self.connection, config=config
        )

    def test_status_running(self):
        session, ec2, _ssm = _make_mocks(instance=_make_instance("i-live"))
        provider = AwsEc2Provider(
            user=self.user, connection=self.connection
        )
        with patch.object(provider, "get_session", return_value=session):
            live = provider.get_status("i-live")

        self.assertEqual(live["status"], DeploymentStatus.RUNNING)
        self.assertEqual(live["progress"], 100)
        self.assertEqual(live["provider_type"], "AWS")
        self.assertEqual(live["ip_address"], "13.232.1.10")

    def test_status_pending_maps_to_building(self):
        session, ec2, _ssm = _make_mocks(
            instance=_make_instance("i-live", state="pending", ip="")
        )
        provider = AwsEc2Provider(
            user=self.user, connection=self.connection
        )
        with patch.object(provider, "get_session", return_value=session):
            live = provider.get_status("i-live")
        self.assertEqual(live["status"], DeploymentStatus.BUILDING)

    def test_status_terminated_maps_to_failed(self):
        session, ec2, _ssm = _make_mocks(
            instance=_make_instance("i-live", state="terminated", ip="")
        )
        provider = AwsEc2Provider(
            user=self.user, connection=self.connection
        )
        with patch.object(provider, "get_session", return_value=session):
            live = provider.get_status("i-live")
        self.assertEqual(live["status"], DeploymentStatus.FAILED)

    def test_status_unknown_instance_raises(self):
        session, ec2, _ssm = _make_mocks()
        ec2.describe_instances.return_value = {"Reservations": []}
        provider = AwsEc2Provider(
            user=self.user, connection=self.connection
        )
        with patch.object(provider, "get_session", return_value=session):
            with self.assertRaises(AwsEc2Error):
                provider.get_status("i-missing")

    def test_health_check_healthy_when_running(self):
        session, ec2, _ssm = _make_mocks(instance=_make_instance("i-live"))
        provider = AwsEc2Provider(
            user=self.user, connection=self.connection
        )
        with patch.object(provider, "get_session", return_value=session):
            health = provider.health_check("i-live")
        self.assertTrue(health["healthy"])
        self.assertEqual(health["provider_type"], "AWS")

    def test_health_check_unhealthy_when_terminated(self):
        session, ec2, _ssm = _make_mocks(
            instance=_make_instance("i-live", state="terminated", ip="")
        )
        provider = AwsEc2Provider(
            user=self.user, connection=self.connection
        )
        with patch.object(provider, "get_session", return_value=session):
            health = provider.health_check("i-live")
        self.assertFalse(health["healthy"])

    def test_get_logs_returns_stored_entries(self):
        provider = AwsEc2Provider(
            user=self.user, connection=self.connection
        )
        EC2Instance.objects.filter(instance_id="i-live").update(
            metadata={
                "logs": [
                    {
                        "timestamp": "2026-01-01T00:00:00Z",
                        "level": "INFO",
                        "stage": "COMPLETED",
                        "message": "provisioned",
                    }
                ]
            }
        )
        logs = provider.get_logs("i-live")
        self.assertEqual(len(logs), 1)
        self.assertEqual(logs[0]["stage"], "COMPLETED")

    def test_rollback_retains_instance_and_returns_rolled_back(self):
        provider = AwsEc2Provider(
            user=self.user, connection=self.connection
        )
        result = provider.rollback("i-live")

        self.assertEqual(result["status"], DeploymentStatus.ROLLED_BACK)
        self.assertEqual(result["provider_type"], "AWS")
        self.assertIn("retained", result["message"])
        # Instance is NOT terminated by rollback (no containers yet)
        self.assertTrue(
            EC2Instance.objects.filter(instance_id="i-live").exists()
        )
        stages = [log["stage"] for log in result["logs"]]
        self.assertIn("ROLLBACK", stages)

    def test_deploy_requires_files_and_instance(self):
        provider = AwsEc2Provider(
            user=self.user, connection=self.connection
        )
        with self.assertRaises(AwsEc2Error):
            provider.deploy({})  # no instance_id / files
        with self.assertRaises(AwsEc2Error):
            provider.deploy({"instance_id": "i-0abc123"})  # no files

    @override_settings(AWS_INSTALL_DOCKER=True)
    def test_deploy_uploads_files_and_starts_containers(self):
        session, ec2, ssm = _make_mocks()
        # SSM managed instance registration
        ssm.describe_instance_information.return_value = {
            "InstanceInformationList": [
                {"InstanceId": "i-0abc123", "PingStatus": "Online"}
            ]
        }
        # send_command returns no CommandId → treated as submitted (mock path)
        ssm.send_command.return_value = {}

        EC2Instance.objects.create(
            user=self.user,
            instance_id="i-0abc123",
            region="ap-south-1",
            status="running",
            public_ip="13.232.1.10",
        )
        provider = self._provider()

        with patch.object(provider, "get_session", return_value=session):
            result = provider.deploy(
                {
                    "instance_id": "i-0abc123",
                    "files": {
                        "Dockerfile": "FROM node:20-alpine\n",
                        "docker-compose.yml": "services:\n  app:\n    build: .\n",
                    },
                    "env_vars": {"PORT": "3000"},
                    "project_id": "proj1",
                    "environment_name": "prod",
                    "port": 3000,
                }
            )

        self.assertEqual(result["status"], DeploymentStatus.RUNNING)
        self.assertTrue(result["healthy"])
        self.assertEqual(result["file_count"], 2)
        self.assertEqual(result["env_keys"], ["PORT"])
        self.assertNotIn("3000=PORT", str(result))  # no env values leaked as pairs incorrectly
        self.assertIn("PORT", result["env_keys"])
        # Remote dir is isolated per project
        self.assertIn("/opt/cloudwise/projects/proj1/prod", result["remote_dir"])
        # SSM send_command was used for upload + compose
        self.assertTrue(ssm.send_command.called)
        # Stages walked
        stages = [log["stage"] for log in result["logs"]]
        for expected in ("PREPARING", "BUILDING", "DEPLOYING", "HEALTH_CHECK", "COMPLETED"):
            self.assertIn(expected, stages)

    def test_deploy_rejects_path_traversal(self):
        provider = self._provider()
        with self.assertRaises(AwsEc2Error):
            provider._safe_rel_path("../../etc/passwd")


class NoSecretLeakTests(TestCase):
    def test_status_and_health_payloads_contain_no_credentials(self):
        user = User.objects.create_user(
            username="nosec", password="pass1234", email="nosec@example.com"
        )
        connection = AWSConnection.objects.create(
            user=user,
            role_arn="arn:aws:iam::999988887777:role/CloudWiseDeployRole",
            external_id="cloudwise-nosec",
            account_id="999988887777",
            region="ap-south-1",
            status="active",
        )
        EC2Instance.objects.create(
            user=user, instance_id="i-nosec", status="running"
        )
        session, ec2, _ssm = _make_mocks(instance=_make_instance("i-nosec"))
        provider = AwsEc2Provider(user=user, connection=connection)

        with patch.object(provider, "get_session", return_value=session):
            status_payload = provider.get_status("i-nosec")
            health_payload = provider.health_check("i-nosec")

        blob = str(status_payload).lower() + str(health_payload).lower()
        for keyword in (
            "secret",
            "session_token",
            "aws_access_key",
            "aws_secret",
            "credential",
        ):
            self.assertNotIn(keyword, blob)
