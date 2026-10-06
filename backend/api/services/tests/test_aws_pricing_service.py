from decimal import Decimal
from unittest.mock import patch

from django.test import SimpleTestCase, override_settings

from api.services.aws_pricing_service import (
    AWS_CURATED_INSTANCES,
    AwsPricingError,
    fetch_price_catalog,
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

        # Normalized schema assertions
        self.assertEqual(snapshot['provider'], 'AWS')
        self.assertEqual(snapshot['service'], 'EC2')
        self.assertEqual(snapshot['instanceType'], 'c6i.xlarge')
        self.assertEqual(snapshot['vcpu'], 4)
        self.assertEqual(snapshot['memoryGiB'], 8.0)
        self.assertEqual(snapshot['unit'], 'Hrs')
        self.assertEqual(snapshot['pricePerUnit'], 0.5)
        self.assertEqual(snapshot['currency'], 'USD')
        self.assertEqual(snapshot['pricingModel'], 'OnDemand')
        self.assertIn('fetchedAt', snapshot)

        # Legacy fields preserved
        self.assertEqual(snapshot['hourlyUsd'], 0.5)
        self.assertEqual(snapshot['monthlyUsd'], 365.0)
        self.assertEqual(snapshot['monthlyInr'], 29200)
        self.assertEqual(snapshot['source'], 'AWS Pricing API')

    @patch('api.services.aws_pricing_service.boto3.client')
    def test_rejects_empty_aws_price_response(self, client_factory):
        client_factory.return_value.get_products.return_value = {'PriceList': []}

        with self.assertRaises(AwsPricingError):
            get_aws_price_snapshot()

    @patch('api.services.aws_pricing_service.get_aws_price_snapshot')
    def test_fetch_price_catalog_iterates_curated_instances(self, mock_snapshot):
        mock_snapshot.side_effect = lambda instance_type, region: {
            'provider': 'AWS',
            'service': 'EC2',
            'region': region,
            'sku': f'aws-ec2-{instance_type}',
            'instanceType': instance_type,
            'vcpu': 2,
            'memoryGiB': 4.0,
            'storageType': 'EBS only',
            'unit': 'Hrs',
            'pricePerUnit': 0.10,
            'currency': 'USD',
            'pricingModel': 'OnDemand',
        }

        catalog = fetch_price_catalog()
        self.assertEqual(len(catalog), len(AWS_CURATED_INSTANCES))
        types = [item['instanceType'] for item in catalog]
        self.assertIn('t3.micro', types)
        self.assertIn('c6i.xlarge', types)

    @patch('api.services.aws_pricing_service.get_aws_price_snapshot')
    def test_fetch_price_catalog_degrades_gracefully_on_error(self, mock_snapshot):
        mock_snapshot.side_effect = AwsPricingError("Unable to locate credentials")
        catalog = fetch_price_catalog()
        self.assertEqual(catalog, [])