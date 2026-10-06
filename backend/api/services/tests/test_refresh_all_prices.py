from io import StringIO
from unittest.mock import patch

from django.core.management import call_command
from django.test import TestCase

from api.models import PriceSnapshot


class RefreshAllPricesCommandTests(TestCase):
    def setUp(self):
        PriceSnapshot.objects.all().delete()

    @patch('api.services.aws_pricing_service.fetch_price_catalog')
    @patch('api.services.azure_pricing_service.fetch_price_catalog')
    @patch('api.services.gcp_pricing_service.fetch_price_catalog')
    def test_refresh_all_prices_upserts_all_providers(
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
        call_command('refresh_all_prices', stdout=out)

        self.assertEqual(PriceSnapshot.objects.count(), 3)
        providers_saved = set(PriceSnapshot.objects.values_list('provider', flat=True))
        self.assertEqual(providers_saved, {'AWS', 'Azure', 'GCP'})

    @patch('api.services.aws_pricing_service.fetch_price_catalog')
    @patch('api.services.azure_pricing_service.fetch_price_catalog')
    @patch('api.services.gcp_pricing_service.fetch_price_catalog')
    def test_refresh_continues_on_partial_provider_failure(
        self, mock_gcp, mock_azure, mock_aws
    ):
        mock_aws.return_value = [{
            'provider': 'AWS',
            'service': 'EC2',
            'region': 'Asia Pacific (Mumbai)',
            'sku': 'aws-c6i.large',
            'instanceType': 'c6i.large',
            'vcpu': 2,
            'memoryGiB': 4.0,
            'storageType': 'EBS only',
            'unit': 'Hrs',
            'pricePerUnit': 0.085,
            'currency': 'USD',
            'pricingModel': 'OnDemand',
        }]

        # Azure fails with an error (e.g. rate limit, connection error)
        mock_azure.side_effect = RuntimeError("Azure retail API network connection timeout")

        mock_gcp.return_value = [{
            'provider': 'GCP',
            'service': 'Compute Engine',
            'region': 'asia-south1',
            'sku': 'gcp-e2-standard-2',
            'instanceType': 'e2-standard-2',
            'vcpu': 2,
            'memoryGiB': 8.0,
            'storageType': 'Persistent Disk',
            'unit': 'Hrs',
            'pricePerUnit': 0.067,
            'currency': 'USD',
            'pricingModel': 'OnDemand',
        }]

        out = StringIO()
        err = StringIO()
        call_command('refresh_all_prices', stdout=out, stderr=err)

        # AWS and GCP should be saved; Azure skipped
        self.assertEqual(PriceSnapshot.objects.count(), 2)
        providers_saved = set(PriceSnapshot.objects.values_list('provider', flat=True))
        self.assertEqual(providers_saved, {'AWS', 'GCP'})
        self.assertNotIn('Azure', providers_saved)
        self.assertIn("Failed to refresh prices for provider Azure", err.getvalue())

    @patch('api.services.aws_pricing_service.fetch_price_catalog')
    @patch('api.services.azure_pricing_service.fetch_price_catalog')
    @patch('api.services.gcp_pricing_service.fetch_price_catalog')
    def test_refresh_all_prices_all_providers_missing_or_empty(
        self, mock_gcp, mock_azure, mock_aws
    ):
        mock_aws.return_value = []
        mock_azure.return_value = []
        mock_gcp.return_value = []

        out = StringIO()
        err = StringIO()
        call_command('refresh_all_prices', stdout=out, stderr=err)

        self.assertEqual(PriceSnapshot.objects.count(), 0)
        self.assertIn("Completed refresh. Total snapshots upserted: 0.", out.getvalue())
