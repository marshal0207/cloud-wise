from datetime import timedelta
from decimal import Decimal
from io import StringIO
from unittest.mock import MagicMock, patch

from django.core.management import call_command
from django.test import TestCase
from django.utils import timezone

from api.models import CloudPricingCache


class RefreshPricingCommandTests(TestCase):
    def setUp(self):
        CloudPricingCache.objects.all().delete()

    @patch('api.management.commands.refresh_pricing.get_gcp_price_snapshot')
    @patch('api.management.commands.refresh_pricing.get_azure_price_snapshot')
    @patch('api.management.commands.refresh_pricing.get_aws_price_snapshot')
    def test_refresh_all_providers_creates_fifteen_cache_entries(
        self, mock_aws, mock_azure, mock_gcp
    ):
        mock_aws.return_value = {
            'provider': 'AWS',
            'instanceType': 'c6i.xlarge',
            'region': 'Asia Pacific (Mumbai)',
            'hourlyUsd': 0.17,
            'monthlyUsd': 124.1,
            'usdToInrRate': 83.0,
            'monthlyInr': 10300,
            'source': 'AWS Pricing API',
            'specs': {'vcpu': 4, 'ramGB': 16, 'storageGB': 100},
        }
        mock_azure.return_value = {
            'provider': 'Azure',
            'instanceType': 'Standard_D4s_v5',
            'region': 'Asia Pacific (Mumbai)',
            'hourlyUsd': 0.192,
            'monthlyUsd': 140.16,
            'usdToInrRate': 83.0,
            'monthlyInr': 11633,
            'source': 'Azure Retail Prices API',
            'specs': {'vcpu': 4, 'ramGB': 16, 'storageGB': 100},
        }
        mock_gcp.return_value = {
            'provider': 'GCP',
            'instanceType': 'e2-custom-4-16384',
            'region': 'Asia Pacific (Mumbai)',
            'hourlyUsd': 0.146,
            'monthlyUsd': 106.58,
            'usdToInrRate': 83.0,
            'monthlyInr': 8846,
            'source': 'GCP Pricing (Estimated Fallback)',
            'specs': {'vcpu': 4, 'ramGB': 16, 'storageGB': 100},
        }

        out = StringIO()
        call_command('refresh_pricing', force=True, stdout=out)

        # 5 tiers * 3 providers = 15 rows
        self.assertEqual(CloudPricingCache.objects.count(), 15)
        self.assertEqual(CloudPricingCache.objects.filter(provider='AWS').count(), 5)
        self.assertEqual(CloudPricingCache.objects.filter(provider='Azure').count(), 5)
        self.assertEqual(CloudPricingCache.objects.filter(provider='GCP').count(), 5)

        sample = CloudPricingCache.objects.filter(provider='AWS').first()
        self.assertIsNotNone(sample)
        self.assertEqual(sample.price_per_month, Decimal('10300.00'))
        self.assertIn('Refresh Complete!', out.getvalue())

    @patch('api.management.commands.refresh_pricing.get_gcp_price_snapshot')
    @patch('api.management.commands.refresh_pricing.get_azure_price_snapshot')
    @patch('api.management.commands.refresh_pricing.get_aws_price_snapshot')
    def test_skips_recent_entries_unless_forced(
        self, mock_aws, mock_azure, mock_gcp
    ):
        mock_aws.return_value = {
            'provider': 'AWS',
            'instanceType': 't3.small',
            'region': 'Asia Pacific (Mumbai)',
            'hourlyUsd': 0.02,
            'monthlyUsd': 15.0,
            'usdToInrRate': 83.0,
            'monthlyInr': 1245,
            'source': 'AWS Pricing API',
            'specs': {'vcpu': 1, 'ramGB': 2, 'storageGB': 30},
        }

        # Pre-seed one recent cache entry
        CloudPricingCache.objects.create(
            provider='AWS',
            instance_type='t3.small',
            region='Asia Pacific (Mumbai)',
            price_per_month=Decimal('1245.00'),
            hourly_usd=Decimal('0.02'),
            specs={'vcpu': 1, 'ramGB': 2},
            source='Pre-cached',
        )

        out = StringIO()
        # Run without force for AWS only
        call_command('refresh_pricing', provider='AWS', stdout=out)

        # t3.small should have been skipped, the other 4 AWS tiers fetched
        self.assertIn('Skipped', out.getvalue())
        self.assertEqual(mock_aws.call_count, 4)

        # Now run with force=True
        mock_aws.reset_mock()
        out_force = StringIO()
        call_command('refresh_pricing', provider='AWS', force=True, stdout=out_force)
        self.assertEqual(mock_aws.call_count, 5)

    @patch('api.management.commands.refresh_pricing.get_gcp_price_snapshot')
    @patch('api.management.commands.refresh_pricing.get_azure_price_snapshot')
    @patch('api.management.commands.refresh_pricing.get_aws_price_snapshot')
    def test_filter_by_single_provider(
        self, mock_aws, mock_azure, mock_gcp
    ):
        mock_azure.return_value = {
            'provider': 'Azure',
            'instanceType': 'Standard_D4s_v5',
            'region': 'Asia Pacific (Mumbai)',
            'hourlyUsd': 0.192,
            'monthlyUsd': 140.16,
            'usdToInrRate': 83.0,
            'monthlyInr': 11633,
            'source': 'Azure Retail Prices API',
            'specs': {'vcpu': 4, 'ramGB': 16, 'storageGB': 100},
        }

        call_command('refresh_pricing', provider='Azure', force=True)

        self.assertEqual(CloudPricingCache.objects.count(), 5)
        self.assertEqual(CloudPricingCache.objects.filter(provider='Azure').count(), 5)
        self.assertEqual(CloudPricingCache.objects.filter(provider='AWS').count(), 0)
        self.assertEqual(CloudPricingCache.objects.filter(provider='GCP').count(), 0)
        self.assertEqual(mock_aws.call_count, 0)
        self.assertEqual(mock_gcp.call_count, 0)

    @patch('api.management.commands.refresh_pricing.get_aws_price_snapshot')
    def test_handles_fetch_error_gracefully(self, mock_aws):
        mock_aws.side_effect = RuntimeError('Connection timeout')

        out = StringIO()
        err = StringIO()
        call_command('refresh_pricing', provider='AWS', force=True, stdout=out, stderr=err)

        self.assertEqual(CloudPricingCache.objects.count(), 0)
        self.assertIn('Error: Connection timeout', err.getvalue())
        self.assertIn('Errors: 5', out.getvalue())
