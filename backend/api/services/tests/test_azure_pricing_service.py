import urllib.error
from unittest.mock import MagicMock, patch

from django.test import SimpleTestCase

from api.services.azure_pricing_service import (
    AzurePricingError,
    fetch_price_catalog,
)


class AzurePricingServiceTests(SimpleTestCase):
    @patch('api.services.azure_pricing_service._fetch_azure_page')
    def test_fetches_and_normalizes_azure_prices(self, mock_fetch):
        mock_fetch.return_value = {
            'Items': [
                {
                    'currencyCode': 'USD',
                    'retailPrice': 0.192,
                    'unitOfMeasure': '1 Hour',
                    'armRegionName': 'centralindia',
                    'armSkuName': 'Standard_D4s_v5',
                    'meterName': 'D4s v5',
                    'productName': 'Virtual Machines Dsv5 Series',
                    'skuId': 'azure-sku-d4s-v5',
                },
                # Exclude Windows license
                {
                    'currencyCode': 'USD',
                    'retailPrice': 0.350,
                    'unitOfMeasure': '1 Hour',
                    'armRegionName': 'centralindia',
                    'armSkuName': 'Standard_D4s_v5',
                    'meterName': 'D4s v5',
                    'productName': 'Virtual Machines Dsv5 Series Windows',
                    'skuId': 'azure-sku-d4s-v5-win',
                },
                # Exclude Spot instance
                {
                    'currencyCode': 'USD',
                    'retailPrice': 0.040,
                    'unitOfMeasure': '1 Hour',
                    'armRegionName': 'centralindia',
                    'armSkuName': 'Standard_D4s_v5',
                    'meterName': 'D4s v5 Spot',
                    'productName': 'Virtual Machines Dsv5 Series',
                    'skuId': 'azure-sku-d4s-v5-spot',
                },
                # Other curated VM
                {
                    'currencyCode': 'USD',
                    'retailPrice': 0.048,
                    'unitOfMeasure': '1 Hour',
                    'armRegionName': 'centralindia',
                    'armSkuName': 'Standard_B2s',
                    'meterName': 'B2s',
                    'productName': 'Virtual Machines BS Series',
                    'skuId': 'azure-sku-b2s',
                },
            ],
            'NextPageLink': None,
        }

        catalog = fetch_price_catalog()
        self.assertEqual(len(catalog), 2)

        d4s = next(item for item in catalog if item['instanceType'] == 'Standard_D4s_v5')
        self.assertEqual(d4s['provider'], 'Azure')
        self.assertEqual(d4s['service'], 'Virtual Machines')
        self.assertEqual(d4s['region'], 'centralindia')
        self.assertEqual(d4s['sku'], 'azure-sku-d4s-v5')
        self.assertEqual(d4s['vcpu'], 4)
        self.assertEqual(d4s['memoryGiB'], 16.0)
        self.assertEqual(d4s['pricePerUnit'], 0.192)
        self.assertEqual(d4s['currency'], 'USD')
        self.assertEqual(d4s['pricingModel'], 'Consumption')
        self.assertEqual(d4s['unit'], 'Hrs')

        b2s = next(item for item in catalog if item['instanceType'] == 'Standard_B2s')
        self.assertEqual(b2s['vcpu'], 2)
        self.assertEqual(b2s['memoryGiB'], 4.0)
        self.assertEqual(b2s['pricePerUnit'], 0.048)

    @patch('api.services.azure_pricing_service._fetch_azure_page')
    def test_handles_api_failure(self, mock_fetch):
        mock_fetch.side_effect = AzurePricingError("Azure Pricing API request failed")

        catalog = fetch_price_catalog()
        self.assertEqual(catalog, [])
