from decimal import Decimal
from unittest.mock import MagicMock, patch

from django.test import SimpleTestCase

from api.services.azure_pricing_service import (
    AzurePricingError,
    get_azure_hourly_price,
    get_azure_price_snapshot,
    get_closest_azure_sku,
)


class AzurePricingServiceTests(SimpleTestCase):
    def test_sku_resolution_by_spec(self):
        self.assertEqual(get_closest_azure_sku(1, 1), 'Standard_B1s')
        self.assertEqual(get_closest_azure_sku(1, 2), 'Standard_B1ms')
        self.assertEqual(get_closest_azure_sku(2, 8), 'Standard_D2s_v5')
        self.assertEqual(get_closest_azure_sku(4, 16), 'Standard_D4s_v5')
        self.assertEqual(get_closest_azure_sku(8, 32), 'Standard_D8s_v5')
        self.assertEqual(get_closest_azure_sku(16, 64), 'Standard_D16s_v5')
        self.assertEqual(get_closest_azure_sku(32, 128), 'Standard_D32s_v5')
        self.assertEqual(get_closest_azure_sku(64, 256), 'Standard_D64s_v5')

    @patch('api.services.azure_pricing_service.requests.get')
    def test_live_azure_pricing_snapshot(self, mock_get):
        mock_response = MagicMock()
        mock_response.json.return_value = {
            'Items': [
                {
                    'armSkuName': 'Standard_D4s_v5',
                    'retailPrice': 0.192,
                    'unitOfMeasure': '1 Hour',
                    'meterName': 'D4s v5',
                }
            ]
        }
        mock_response.raise_for_status.return_value = None
        mock_get.return_value = mock_response

        with patch.dict('os.environ', {'USD_TO_INR_RATE': '80'}):
            snapshot = get_azure_price_snapshot(vcpu=4, ram_gb=16, region='Asia Pacific (Mumbai)')

        self.assertEqual(snapshot['provider'], 'Azure')
        self.assertEqual(snapshot['instanceType'], 'Standard_D4s_v5')
        self.assertEqual(snapshot['armRegion'], 'westindia')
        self.assertEqual(snapshot['hourlyUsd'], 0.192)
        self.assertEqual(snapshot['monthlyUsd'], 140.16)
        self.assertEqual(snapshot['monthlyInr'], 11213)
        self.assertEqual(snapshot['source'], 'Azure Retail Prices API')
        self.assertFalse(snapshot['estimated'])

    @patch('api.services.azure_pricing_service.requests.get')
    def test_fallback_when_azure_api_fails(self, mock_get):
        mock_get.side_effect = Exception('Azure API timeout')

        with patch.dict('os.environ', {'USD_TO_INR_RATE': '80'}):
            snapshot = get_azure_price_snapshot(vcpu=4, ram_gb=16, region='Asia Pacific (Mumbai)')

        self.assertEqual(snapshot['provider'], 'Azure')
        self.assertEqual(snapshot['instanceType'], 'Standard_D4s_v5')
        self.assertTrue(snapshot['estimated'])
        self.assertEqual(snapshot['source'], 'Azure Pricing (Estimated Fallback)')
        self.assertGreater(snapshot['monthlyInr'], 0)
