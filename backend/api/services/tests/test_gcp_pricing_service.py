from decimal import Decimal
from unittest.mock import MagicMock, patch

from django.test import SimpleTestCase

from api.services.gcp_pricing_service import (
    build_gcp_custom_machine_type,
    fetch_gcp_rates_from_catalog,
    get_gcp_price_snapshot,
    GcpPricingError,
)


class GcpPricingServiceTests(SimpleTestCase):
    def test_custom_machine_type_format(self):
        self.assertEqual(build_gcp_custom_machine_type(4, 16), 'e2-custom-4-16384')
        self.assertEqual(build_gcp_custom_machine_type(2, 8), 'e2-custom-2-8192')
        self.assertEqual(build_gcp_custom_machine_type(8, 32), 'e2-custom-8-32768')

    def test_fallback_when_api_key_absent(self):
        with patch.dict('os.environ', {'GCP_API_KEY': '', 'USD_TO_INR_RATE': '80'}):
            snapshot = get_gcp_price_snapshot(vcpu=4, ram_gb=16, region='Asia Pacific (Mumbai)')

        self.assertEqual(snapshot['provider'], 'GCP')
        self.assertEqual(snapshot['instanceType'], 'e2-custom-4-16384')
        self.assertEqual(snapshot['gcpRegion'], 'asia-south1')
        self.assertTrue(snapshot['estimated'])
        self.assertEqual(snapshot['source'], 'GCP Pricing (Estimated Fallback)')
        self.assertGreater(snapshot['hourlyUsd'], 0)
        self.assertGreater(snapshot['monthlyInr'], 0)

    @patch('api.services.gcp_pricing_service.requests.get')
    def test_live_gcp_pricing_with_api_key(self, mock_get):
        mock_response = MagicMock()
        mock_response.json.return_value = {
            'skus': [
                {
                    'description': 'E2 Instance Core running in Mumbai',
                    'serviceRegions': ['asia-south1'],
                    'pricingInfo': [
                        {
                            'pricingExpression': {
                                'tieredRates': [
                                    {
                                        'unitPrice': {
                                            'units': '0',
                                            'nanos': 23797000,  # $0.023797
                                        }
                                    }
                                ]
                            }
                        }
                    ],
                },
                {
                    'description': 'E2 Instance Ram running in Mumbai',
                    'serviceRegions': ['asia-south1'],
                    'pricingInfo': [
                        {
                            'pricingExpression': {
                                'tieredRates': [
                                    {
                                        'unitPrice': {
                                            'units': '0',
                                            'nanos': 3189000,  # $0.003189
                                        }
                                    }
                                ]
                            }
                        }
                    ],
                },
            ]
        }
        mock_response.raise_for_status.return_value = None
        mock_get.return_value = mock_response

        with patch.dict('os.environ', {'GCP_API_KEY': 'test-gcp-key', 'USD_TO_INR_RATE': '80'}):
            snapshot = get_gcp_price_snapshot(vcpu=4, ram_gb=16, region='Asia Pacific (Mumbai)')

        self.assertEqual(snapshot['provider'], 'GCP')
        self.assertEqual(snapshot['instanceType'], 'e2-custom-4-16384')
        self.assertFalse(snapshot['estimated'])
        self.assertEqual(snapshot['source'], 'GCP Cloud Billing Catalog API')
        expected_hourly = (4 * 0.023797) + (16 * 0.003189)
        self.assertAlmostEqual(snapshot['hourlyUsd'], expected_hourly, places=4)
