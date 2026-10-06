import json
import urllib.error
from unittest.mock import MagicMock, patch

from django.test import SimpleTestCase

from api.services.gcp_pricing_service import (
    GCP_CURATED_MACHINES,
    fetch_price_catalog,
)


class GcpPricingServiceTests(SimpleTestCase):
    def test_skips_gracefully_when_api_key_missing(self):
        with patch.dict('os.environ', {}, clear=True):
            catalog = fetch_price_catalog()
            self.assertEqual(catalog, [])

    @patch('api.services.gcp_pricing_service.urllib.request.urlopen')
    def test_fetches_and_calculates_gcp_catalog(self, mock_urlopen):
        # Mock GCP Cloud Billing Catalog API response
        api_response = {
            'skus': [
                {
                    'skuId': 'E2-Core-Mumbai',
                    'description': 'E2 Instance Core running in Mumbai',
                    'serviceRegions': ['asia-south1'],
                    'pricingInfo': [{
                        'pricingExpression': {
                            'tieredRates': [{
                                'unitPrice': {'units': '0', 'nanos': 24900000}  # $0.0249 / vcpu-hr
                            }]
                        }
                    }]
                },
                {
                    'skuId': 'E2-Ram-Mumbai',
                    'description': 'E2 Instance Ram running in Mumbai',
                    'serviceRegions': ['asia-south1'],
                    'pricingInfo': [{
                        'pricingExpression': {
                            'tieredRates': [{
                                'unitPrice': {'units': '0', 'nanos': 3340000}  # $0.00334 / GB-hr
                            }]
                        }
                    }]
                },
                {
                    'skuId': 'N2-Core-Mumbai',
                    'description': 'N2 Instance Core running in Mumbai',
                    'serviceRegions': ['asia-south1'],
                    'pricingInfo': [{
                        'pricingExpression': {
                            'tieredRates': [{
                                'unitPrice': {'units': '0', 'nanos': 34700000}
                            }]
                        }
                    }]
                },
                {
                    'skuId': 'N2-Ram-Mumbai',
                    'description': 'N2 Instance Ram running in Mumbai',
                    'serviceRegions': ['asia-south1'],
                    'pricingInfo': [{
                        'pricingExpression': {
                            'tieredRates': [{
                                'unitPrice': {'units': '0', 'nanos': 4650000}
                            }]
                        }
                    }]
                },
            ],
            'nextPageToken': None,
        }

        mock_context = MagicMock()
        mock_context.read.return_value = json.dumps(api_response).encode('utf-8')
        mock_urlopen.return_value.__enter__.return_value = mock_context

        with patch.dict('os.environ', {'GCP_BILLING_API_KEY': 'test-fake-key'}):
            catalog = fetch_price_catalog()

        self.assertEqual(len(catalog), len(GCP_CURATED_MACHINES))

        # Check e2-standard-2 (2 vcpu, 8 GiB ram)
        e2_std2 = next(item for item in catalog if item['instanceType'] == 'e2-standard-2')
        self.assertEqual(e2_std2['provider'], 'GCP')
        self.assertEqual(e2_std2['service'], 'Compute Engine')
        self.assertEqual(e2_std2['region'], 'asia-south1')
        self.assertEqual(e2_std2['vcpu'], 2)
        self.assertEqual(e2_std2['memoryGiB'], 8.0)
        self.assertEqual(e2_std2['unit'], 'Hrs')
        self.assertEqual(e2_std2['currency'], 'USD')
        self.assertEqual(e2_std2['pricingModel'], 'OnDemand')
        expected_price = round(2 * 0.0249 + 8 * 0.00334, 4)
        self.assertEqual(e2_std2['pricePerUnit'], expected_price)

    @patch('api.services.gcp_pricing_service.urllib.request.urlopen')
    def test_degrades_gracefully_on_http_error(self, mock_urlopen):
        mock_urlopen.side_effect = urllib.error.HTTPError(
            url='https://cloudbilling.googleapis.com',
            code=403,
            msg='Forbidden',
            hdrs={},
            fp=None
        )

        with patch.dict('os.environ', {'GCP_BILLING_API_KEY': 'invalid-key'}):
            catalog = fetch_price_catalog()
            self.assertEqual(catalog, [])
