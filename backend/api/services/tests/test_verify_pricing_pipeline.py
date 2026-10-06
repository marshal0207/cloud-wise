from io import StringIO
from unittest.mock import patch

from django.core.management import call_command
from django.test import TestCase

from api.models import PriceSnapshot


class VerifyPricingPipelineCommandTests(TestCase):
    def setUp(self):
        PriceSnapshot.objects.all().delete()

    @patch('api.services.aws_pricing_service.fetch_price_catalog')
    @patch('api.services.azure_pricing_service.fetch_price_catalog')
    @patch('api.services.gcp_pricing_service.fetch_price_catalog')
    def test_verify_pipeline_success_with_three_providers(
        self, mock_gcp, mock_azure, mock_aws
    ):
        mock_aws.return_value = [{
            'provider': 'AWS',
            'service': 'EC2',
            'region': 'Asia Pacific (Mumbai)',
            'sku': 'aws-t3.micro',
            'instanceType': 't3.micro',
            'vcpu': 2,
            'memoryGiB': 1.0,
            'storageType': 'EBS only',
            'unit': 'Hrs',
            'pricePerUnit': 0.0104,
            'currency': 'USD',
            'pricingModel': 'OnDemand',
        }]
        mock_azure.return_value = [{
            'provider': 'Azure',
            'service': 'Virtual Machines',
            'region': 'centralindia',
            'sku': 'azure-b1s',
            'instanceType': 'Standard_B1s',
            'vcpu': 1,
            'memoryGiB': 1.0,
            'storageType': 'Remote SSD',
            'unit': 'Hrs',
            'pricePerUnit': 0.012,
            'currency': 'USD',
            'pricingModel': 'Consumption',
        }]
        mock_gcp.return_value = [{
            'provider': 'GCP',
            'service': 'Compute Engine',
            'region': 'asia-south1',
            'sku': 'gcp-e2-micro',
            'instanceType': 'e2-micro',
            'vcpu': 2,
            'memoryGiB': 1.0,
            'storageType': 'Persistent Disk',
            'unit': 'Hrs',
            'pricePerUnit': 0.0084,
            'currency': 'USD',
            'pricingModel': 'OnDemand',
        }]

        out = StringIO()
        call_command('verify_pricing_pipeline', stdout=out)
        output = out.getvalue()

        self.assertIn("Target providers : AWS, Azure, GCP", output)
        self.assertIn("DigitalOcean (not implemented / optional)", output)
        self.assertIn("[OK]       AWS           :    1 rows in DB", output)
        self.assertIn("[OK]       Azure         :    1 rows in DB", output)
        self.assertIn("[OK]       GCP           :    1 rows in DB", output)
        self.assertIn("[EXPECTED] DigitalOcean  :    0 rows (not implemented / skipped)", output)
        self.assertIn("OVERALL STATUS: PASS", output)

        # Assert no DO rows exist in DB
        self.assertEqual(PriceSnapshot.objects.filter(provider='DigitalOcean').count(), 0)
        self.assertEqual(PriceSnapshot.objects.count(), 3)

    @patch('api.services.aws_pricing_service.fetch_price_catalog')
    @patch('api.services.azure_pricing_service.fetch_price_catalog')
    @patch('api.services.gcp_pricing_service.fetch_price_catalog')
    def test_verify_pipeline_flags_zero_row_provider(
        self, mock_gcp, mock_azure, mock_aws
    ):
        mock_aws.side_effect = RuntimeError("AWS credentials missing")
        mock_azure.return_value = [{
            'provider': 'Azure',
            'service': 'Virtual Machines',
            'region': 'centralindia',
            'sku': 'azure-b1s',
            'instanceType': 'Standard_B1s',
            'vcpu': 1,
            'memoryGiB': 1.0,
            'storageType': 'Remote SSD',
            'unit': 'Hrs',
            'pricePerUnit': 0.012,
            'currency': 'USD',
            'pricingModel': 'Consumption',
        }]
        mock_gcp.return_value = []

        out = StringIO()
        call_command('verify_pricing_pipeline', stdout=out)
        output = out.getvalue()

        self.assertIn("[FLAGGED]  AWS           :    0 rows", output)
        self.assertIn("[FLAGGED]  GCP           :    0 rows", output)
        self.assertIn("[OK]       Azure         :    1 rows in DB", output)
        self.assertIn("[EXPECTED] DigitalOcean  :    0 rows", output)
