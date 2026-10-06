from django.test import TestCase
from rest_framework.test import APIClient
from rest_framework import status

from api.models import Project, PriceSnapshot
from api.services.recommendation_service import (
    generate_recommendation,
    NoPriceDataError,
)


class RecommendationServiceTests(TestCase):
    def setUp(self):
        PriceSnapshot.objects.all().delete()
        Project.objects.all().delete()
        self.client = APIClient()

    def _create_snapshot(self, provider, instance_type, vcpu, ram, price_hourly, pricing_model='OnDemand', region='Asia Pacific (Mumbai)'):
        return PriceSnapshot.objects.create(
            provider=provider,
            service='Compute',
            region=region,
            sku=f"{provider.lower()}-{instance_type}",
            instanceType=instance_type,
            vcpu=vcpu,
            memoryGiB=ram,
            storageType='SSD',
            unit='Hrs',
            pricePerUnit=price_hourly,
            currency='USD',
            pricingModel=pricing_model,
        )

    def test_candidate_filtering_excludes_underpowered(self):
        # Requirements: 4 vCPU, 8 GB RAM
        self._create_snapshot('AWS', 't3.small', vcpu=2, ram=2.0, price_hourly=0.02)   # Underpowered vCPU & RAM
        self._create_snapshot('AWS', 'c6i.large', vcpu=2, ram=4.0, price_hourly=0.08)  # Underpowered vCPU & RAM
        self._create_snapshot('Azure', 'D4s_v5', vcpu=4, ram=16.0, price_hourly=0.19)  # Meets requirement
        self._create_snapshot('GCP', 'e2-standard-4', vcpu=4, ram=16.0, price_hourly=0.13) # Meets requirement

        result = generate_recommendation({
            'vcpu': 4,
            'ramGB': 8.0,
            'region': 'Asia Pacific (Mumbai)',
            'preference': 'balanced'
        })

        self.assertTrue(result['matchedExactly'])
        recommended = result['recommended']
        self.assertIn(recommended['instanceType'], ['D4s_v5', 'e2-standard-4'])
        self.assertGreaterEqual(recommended['vcpu'], 4)
        self.assertGreaterEqual(recommended['memoryGiB'], 8.0)

        # Confirm underpowered candidates are not in alternatives
        for alt in result['alternatives']:
            self.assertGreaterEqual(alt['vcpu'], 4)
            self.assertGreaterEqual(alt['memoryGiB'], 8.0)

    def test_preference_weighting_cost_mode_picks_cheapest(self):
        # Both meet 2 vCPU / 4 GB RAM requirement
        self._create_snapshot('Azure', 'Standard_B2s', vcpu=2, ram=4.0, price_hourly=0.0416)
        self._create_snapshot('AWS', 'c6i.large', vcpu=2, ram=4.0, price_hourly=0.0850)

        result = generate_recommendation({
            'vcpu': 2,
            'ramGB': 4.0,
            'region': 'Asia Pacific (Mumbai)',
            'preference': 'cost'
        })

        recommended = result['recommended']
        self.assertEqual(recommended['instanceType'], 'Standard_B2s')
        self.assertEqual(recommended['provider'], 'Azure')
        self.assertEqual(recommended['monthlyCostUsd'], round(0.0416 * 730, 2))

    def test_preference_weighting_performance_favors_headroom(self):
        # Requirements: 2 vCPU, 4 GB RAM
        # Option A: Exact minimum capacity (1.0x headroom)
        self._create_snapshot('AWS', 't3.medium', vcpu=2, ram=4.0, price_hourly=0.0416)
        # Option B: Ideal headroom (1.4x - 1.5x) with slightly higher price
        self._create_snapshot('AWS', 'c6i.xlarge', vcpu=4, ram=8.0, price_hourly=0.0520)

        result = generate_recommendation({
            'vcpu': 2,
            'ramGB': 4.0,
            'region': 'Asia Pacific (Mumbai)',
            'preference': 'performance'
        })

        recommended = result['recommended']
        self.assertEqual(recommended['instanceType'], 'c6i.xlarge')
        self.assertEqual(recommended['vcpu'], 4)
        self.assertEqual(recommended['memoryGiB'], 8.0)

    def test_preference_weighting_balanced_mode(self):
        self._create_snapshot('AWS', 't3.micro', vcpu=2, ram=1.0, price_hourly=0.0104)
        self._create_snapshot('Azure', 'Standard_B1s', vcpu=1, ram=1.0, price_hourly=0.0120)
        self._create_snapshot('GCP', 'e2-micro', vcpu=2, ram=1.0, price_hourly=0.0084)

        result = generate_recommendation({
            'vcpu': 1,
            'ramGB': 1.0,
            'region': 'Asia Pacific (Mumbai)',
            'preference': 'balanced'
        })

        self.assertIn('recommended', result)
        self.assertIn('alternatives', result)
        self.assertTrue(result['matchedExactly'])
        self.assertGreater(result['recommended']['score'], 0)

    def test_reasoning_string_contains_actual_computed_numbers(self):
        self._create_snapshot('GCP', 'e2-micro', vcpu=2, ram=1.0, price_hourly=0.0084)
        self._create_snapshot('AWS', 't3.micro', vcpu=2, ram=1.0, price_hourly=0.0104)

        result = generate_recommendation({
            'vcpu': 2,
            'ramGB': 1.0,
            'region': 'Asia Pacific (Mumbai)',
            'preference': 'cost'
        })

        rec = result['recommended']
        reasoning = rec['reasoning']

        # Must include provider and instanceType
        self.assertIn(rec['provider'], reasoning)
        self.assertIn(rec['instanceType'], reasoning)

        # Must include the exact monthly cost formatted
        cost_str = f"${rec['monthlyCostUsd']:.2f}/mo"
        self.assertIn(cost_str, reasoning)

        # Must include requested vs provided specs
        self.assertIn("2 vCPU / 1.0 GB RAM", reasoning)

        # Must mention computed percentage comparison against runner-up
        self.assertIn("cheaper than the next closest option", reasoning)
        self.assertIn("AWS t3.micro", reasoning)

    def test_graceful_handling_zero_rows_raises_no_price_data_error(self):
        with self.assertRaises(NoPriceDataError):
            generate_recommendation({
                'vcpu': 2,
                'ramGB': 4.0,
                'region': 'Asia Pacific (Mumbai)',
            })

    def test_relaxed_match_when_exact_requirements_exceed_available(self):
        # Only smaller nodes available
        self._create_snapshot('AWS', 't3.micro', vcpu=2, ram=1.0, price_hourly=0.0104)
        self._create_snapshot('Azure', 'Standard_B2s', vcpu=2, ram=4.0, price_hourly=0.0416)

        # Request huge instance: 64 vCPU, 256 GB RAM
        result = generate_recommendation({
            'vcpu': 64,
            'ramGB': 256.0,
            'region': 'Asia Pacific (Mumbai)',
            'preference': 'balanced'
        })

        self.assertFalse(result['matchedExactly'])
        self.assertIsNotNone(result['recommended'])
        self.assertIn("relaxed matching was applied", result['recommended']['reasoning'])

    def test_project_recommend_view_success_and_db_update(self):
        self._create_snapshot('AWS', 'c6i.large', vcpu=2, ram=4.0, price_hourly=0.085)
        self._create_snapshot('Azure', 'Standard_B2s', vcpu=2, ram=4.0, price_hourly=0.048)

        project = Project.objects.create(
            name='Test Recommendation Project',
            estimation={
                'vcpu': 2,
                'ram': 4,
                'storage': 100,
                'region': 'Asia Pacific (Mumbai)',
                'budgetTier': 'Cost Optimized',
            }
        )

        response = self.client.post(
            f'/api/projects/{project.id}/recommend',
            data={'preference': 'cost'},
            format='json'
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        res_data = response.json()
        self.assertTrue(res_data['success'])
        self.assertIn('recommended', res_data['data'])
        self.assertEqual(res_data['data']['recommended']['instanceType'], 'Standard_B2s')

        # Verify Project model was persisted with the new selected_recommendation
        project.refresh_from_db()
        self.assertEqual(project.selected_recommendation['provider'], 'Azure')
        self.assertEqual(project.current_step, 'recommendation')

    def test_project_recommend_view_returns_400_on_empty_db(self):
        project = Project.objects.create(name='Empty DB Project')

        response = self.client.post(
            f'/api/projects/{project.id}/recommend',
            data={},
            format='json'
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        res_data = response.json()
        self.assertFalse(res_data['success'])
        self.assertIn("No PriceSnapshot records found", res_data['error'])
