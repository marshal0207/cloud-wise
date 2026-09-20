from rest_framework.test import APITestCase
from django.test import SimpleTestCase

from api.services.free_tier_policy import (
    FreeTierLimitError,
    validate_free_tier_deployment,
)


class FreeTierPolicyTests(SimpleTestCase):
    def test_accepts_small_single_instance_workload(self):
        result = validate_free_tier_deployment(
            vcpu=2,
            ram_gb=2,
            storage_gb=30,
            instances=1,
        )

        self.assertEqual(result['vCPU'], 2)
        self.assertEqual(result['ramGB'], 2)
        self.assertEqual(result['storageGB'], 30)
        self.assertEqual(result['instances'], 1)

    def test_rejects_large_workload(self):
        with self.assertRaisesRegex(FreeTierLimitError, 'vCPU cannot exceed 2'):
            validate_free_tier_deployment(
                vcpu=8,
                ram_gb=32,
                storage_gb=500,
                instances=3,
            )

    def test_rejects_multiple_instances(self):
        with self.assertRaisesRegex(FreeTierLimitError, 'Instances cannot exceed 1'):
            validate_free_tier_deployment(
                vcpu=2,
                ram_gb=2,
                storage_gb=20,
                instances=2,
            )

    def test_rejects_non_positive_values(self):
        with self.assertRaisesRegex(FreeTierLimitError, 'positive integers'):
            validate_free_tier_deployment(
                vcpu=0,
                ram_gb=2,
                storage_gb=20,
            )


class FreeTierDeploymentApiTests(APITestCase):
    def test_deploy_requires_authentication(self):
        # deploy_view is now authenticated — unauthenticated must return 401
        response = self.client.post(
            '/api/deploy',
            {
                'environmentName': 'free-tier-test',
                'provider': 'AWS',
                'specs': {'vcpu': 8, 'ram': 32, 'storage': '500 GB NVMe SSD'},
            },
            format='json',
        )
        self.assertEqual(response.status_code, 401)
