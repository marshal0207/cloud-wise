from django.test import TestCase
from rest_framework.test import APIClient

from api.models import PriceSnapshot


class PricingCompareViewTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        PriceSnapshot.objects.all().delete()

        # Seed test price snapshots
        PriceSnapshot.objects.create(
            provider='AWS',
            service='EC2',
            region='Asia Pacific (Mumbai)',
            sku='aws-c6i.xlarge',
            instanceType='c6i.xlarge',
            vcpu=4,
            memoryGiB=8.0,
            storageType='EBS only',
            unit='Hrs',
            pricePerUnit=0.17,
            currency='USD',
            pricingModel='OnDemand',
        )
        PriceSnapshot.objects.create(
            provider='Azure',
            service='Virtual Machines',
            region='centralindia',
            sku='azure-d4s-v5',
            instanceType='Standard_D4s_v5',
            vcpu=4,
            memoryGiB=16.0,
            storageType='Remote SSD',
            unit='Hrs',
            pricePerUnit=0.192,
            currency='USD',
            pricingModel='Consumption',
        )
        PriceSnapshot.objects.create(
            provider='GCP',
            service='Compute Engine',
            region='asia-south1',
            sku='gcp-e2-standard-2',
            instanceType='e2-standard-2',
            vcpu=2,
            memoryGiB=8.0,
            storageType='Persistent Disk',
            unit='Hrs',
            pricePerUnit=0.067,
            currency='USD',
            pricingModel='OnDemand',
        )

    def test_returns_results_sorted_by_price_ascending(self):
        response = self.client.get('/api/pricing/compare')
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data['success'])
        self.assertEqual(data['count'], 3)

        prices = [item['pricePerUnit'] for item in data['data']]
        self.assertEqual(prices, sorted(prices))
        # First should be GCP (0.067), last should be Azure (0.192)
        self.assertEqual(data['data'][0]['provider'], 'GCP')
        self.assertEqual(data['data'][-1]['provider'], 'Azure')

    def test_filter_by_min_vcpu(self):
        response = self.client.get('/api/pricing/compare?minVcpu=4')
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data['count'], 2)
        for item in data['data']:
            self.assertGreaterEqual(item['vcpu'], 4)
        instance_types = {item['instanceType'] for item in data['data']}
        self.assertEqual(instance_types, {'c6i.xlarge', 'Standard_D4s_v5'})

    def test_filter_by_min_memory(self):
        response = self.client.get('/api/pricing/compare?minMemoryGiB=16')
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data['count'], 1)
        self.assertEqual(data['data'][0]['instanceType'], 'Standard_D4s_v5')
        self.assertEqual(data['data'][0]['memoryGiB'], 16.0)

    def test_filter_by_provider(self):
        response = self.client.get('/api/pricing/compare?provider=aws')
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data['count'], 1)
        self.assertEqual(data['data'][0]['provider'], 'AWS')
        self.assertEqual(data['data'][0]['instanceType'], 'c6i.xlarge')
