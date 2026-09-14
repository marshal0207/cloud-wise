from decimal import Decimal
from unittest.mock import patch

from django.test import SimpleTestCase, override_settings

from api.services.aws_pricing_service import (
    AwsPricingError,
    get_aws_price_snapshot,
)


class AwsPricingServiceTests(SimpleTestCase):
    @patch('api.services.aws_pricing_service.boto3.client')
    @override_settings()
    def test_calculates_live_snapshot_from_aws_hourly_price(self, client_factory):
        client_factory.return_value.get_products.return_value = {
            'PriceList': [{
                'terms': {
                    'OnDemand': {
                        'term': {
                            'priceDimensions': {
                                'dimension': {
                                    'pricePerUnit': {'USD': '0.50'}
                                }
                            }
                        }
                    }
                }
            }]
        }

        with patch.dict('os.environ', {'USD_TO_INR_RATE': '80'}):
            snapshot = get_aws_price_snapshot('c6i.xlarge')

        self.assertEqual(snapshot['hourlyUsd'], 0.5)
        self.assertEqual(snapshot['monthlyUsd'], 365.0)
        self.assertEqual(snapshot['monthlyInr'], 29200)
        self.assertEqual(snapshot['source'], 'AWS Pricing API')

    @patch('api.services.aws_pricing_service.boto3.client')
    def test_rejects_empty_aws_price_response(self, client_factory):
        client_factory.return_value.get_products.return_value = {'PriceList': []}

        with self.assertRaises(AwsPricingError):
            get_aws_price_snapshot()