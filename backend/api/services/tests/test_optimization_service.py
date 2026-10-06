from django.test import TestCase
from rest_framework.test import APIClient
from rest_framework import status

from api.models import Project, PriceSnapshot, CostDataPoint
from api.services.optimization_service import (
    evaluate_cpu_underutilization,
    evaluate_cpu_overutilization,
    evaluate_storage_underutilization,
    evaluate_idle_workload,
    detect_cost_anomalies,
    generate_optimization_suggestions,
)


class OptimizationServiceTests(TestCase):
    def setUp(self):
        PriceSnapshot.objects.all().delete()
        Project.objects.all().delete()
        CostDataPoint.objects.all().delete()
        self.client = APIClient()

    def test_cpu_underutilization_rule_triggers_on_7_days(self):
        # 7 consecutive days under 20%
        metrics = [{'cpu_percent': 14.0} for _ in range(7)]
        suggestion = evaluate_cpu_underutilization(metrics, baseline_monthly_cost=100.0)

        self.assertIsNotNone(suggestion)
        self.assertEqual(suggestion['type'], 'DOWNSIZE_INSTANCE')
        self.assertEqual(suggestion['category'], 'Compute')
        self.assertEqual(suggestion['severity'], 'HIGH')
        self.assertGreater(suggestion['estimatedSavingsUsd'], 0)
        self.assertIn("under 20% for 7 consecutive days", suggestion['description'])

    def test_cpu_underutilization_rule_does_not_trigger_under_7_days(self):
        # Only 6 days under 20%, then spike
        metrics = [{'cpu_percent': 12.0} for _ in range(6)] + [{'cpu_percent': 25.0}]
        suggestion = evaluate_cpu_underutilization(metrics)
        self.assertIsNone(suggestion)

    def test_cpu_overutilization_rule_triggers_on_3_days(self):
        # 3 consecutive days over 85%
        metrics = [{'cpu_percent': 88.0}, {'cpu_percent': 92.5}, {'cpu_percent': 89.0}]
        suggestion = evaluate_cpu_overutilization(metrics)

        self.assertIsNotNone(suggestion)
        self.assertEqual(suggestion['type'], 'UPSIZE_INSTANCE')
        self.assertEqual(suggestion['severity'], 'HIGH')
        self.assertEqual(suggestion['estimatedSavingsUsd'], 0.0)  # Risk, not cost saving
        self.assertIn("exceeded 85% for 3 consecutive days", suggestion['description'])

    def test_cpu_overutilization_rule_does_not_trigger_on_2_days(self):
        metrics = [{'cpu_percent': 90.0}, {'cpu_percent': 89.0}, {'cpu_percent': 60.0}]
        suggestion = evaluate_cpu_overutilization(metrics)
        self.assertIsNone(suggestion)

    def test_storage_underutilization_rule_triggers(self):
        # 25% utilization on a 200 GB volume
        suggestion = evaluate_storage_underutilization(storage_percent=25.0, provisioned_gb=200.0)

        self.assertIsNotNone(suggestion)
        self.assertEqual(suggestion['type'], 'REDUCE_STORAGE')
        self.assertEqual(suggestion['category'], 'Storage')
        self.assertEqual(suggestion['severity'], 'MEDIUM')
        self.assertGreater(suggestion['estimatedSavingsUsd'], 0)

    def test_storage_underutilization_rule_does_not_trigger_for_small_volume(self):
        # Under 30% but volume is <= 100 GB
        suggestion = evaluate_storage_underutilization(storage_percent=20.0, provisioned_gb=50.0)
        self.assertIsNone(suggestion)

        # Above 30% utilization
        suggestion2 = evaluate_storage_underutilization(storage_percent=45.0, provisioned_gb=200.0)
        self.assertIsNone(suggestion2)

    def test_idle_workload_rule_triggers_on_14_days(self):
        # 14 consecutive days of near-zero CPU and requests
        metrics = [{'cpu_percent': 2.0, 'requests_count': 5} for _ in range(14)]
        suggestion = evaluate_idle_workload(metrics, current_monthly_cost=80.0)

        self.assertIsNotNone(suggestion)
        self.assertEqual(suggestion['type'], 'SHUTDOWN_IDLE')
        self.assertEqual(suggestion['category'], 'Reservation')
        self.assertEqual(suggestion['severity'], 'HIGH')
        self.assertEqual(suggestion['estimatedSavingsUsd'], 80.0)

    def test_idle_workload_rule_does_not_trigger_under_14_days(self):
        metrics = [{'cpu_percent': 2.0, 'requests_count': 5} for _ in range(13)] + [{'cpu_percent': 15.0, 'requests_count': 500}]
        suggestion = evaluate_idle_workload(metrics)
        self.assertIsNone(suggestion)

    def test_anomaly_detection_z_score(self):
        # 20 days of steady $30 cost, then a massive spike to $150
        history = [{'date': f'2026-08-{i+1:02d}', 'costUsd': 30.0 + (i % 2)} for i in range(20)]
        history.append({'date': '2026-08-21', 'costUsd': 150.0})

        anomalies = detect_cost_anomalies(history, threshold_z=3.0)

        self.assertEqual(len(anomalies), 1)
        spike = anomalies[0]
        self.assertEqual(spike['date'], '2026-08-21')
        self.assertEqual(spike['cost'], 150.0)
        self.assertGreater(spike['zScore'], 3.0)
        self.assertEqual(spike['severity'], 'CRITICAL')
        self.assertLess(spike['expectedRange'][1], 150.0)

    def test_project_optimize_endpoint(self):
        project = Project.objects.create(name='Optimization Target Project')

        # Provide custom metrics that trigger downsizing
        custom_metrics = [{'cpu_percent': 15.0, 'requests_count': 500} for _ in range(8)]
        response = self.client.post(
            f'/api/projects/{project.id}/optimize',
            data={'metrics': custom_metrics},
            format='json'
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = response.json()
        self.assertTrue(data['success'])
        self.assertIn('suggestions', data['data'])
        self.assertTrue(any(s['type'] == 'DOWNSIZE_INSTANCE' for s in data['data']['suggestions']))

        # Confirm Project.optimizations JSONField was updated
        project.refresh_from_db()
        self.assertGreater(len(project.optimizations), 0)
