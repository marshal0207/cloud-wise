from datetime import date
from django.test import TestCase
from rest_framework.test import APIClient
from rest_framework import status

from api.models import Project, CostDataPoint
from api.services.synthetic_data_service import generate_project_timeseries
from api.services.forecasting_service import forecast_cost


class SyntheticAndForecastingTests(TestCase):
    def setUp(self):
        CostDataPoint.objects.all().delete()
        Project.objects.all().delete()
        self.client = APIClient()

    def test_synthetic_data_is_deterministic_with_same_seed(self):
        series_a = generate_project_timeseries('proj_test_1', days=30, seed=123, persist=False)
        series_b = generate_project_timeseries('proj_test_2', days=30, seed=123, persist=False)

        costs_a = [p.cost_usd for p in series_a]
        costs_b = [p.cost_usd for p in series_b]
        self.assertEqual(costs_a, costs_b)

    def test_synthetic_data_has_trend_and_weekly_seasonality(self):
        series = generate_project_timeseries('proj_test_trend', days=60, seed=42, persist=False)

        # Upward trend: average of last 10 days > average of first 10 days
        first_10_avg = sum(p.cost_usd for p in series[:10]) / 10
        last_10_avg = sum(p.cost_usd for p in series[-10:]) / 10
        self.assertGreater(last_10_avg, first_10_avg)

        # Weekly seasonality: weekdays average cost > weekend average cost
        weekday_costs = [p.cost_usd for p in series if p.date.weekday() < 5]
        weekend_costs = [p.cost_usd for p in series if p.date.weekday() >= 5]
        avg_weekday = sum(weekday_costs) / len(weekday_costs)
        avg_weekend = sum(weekend_costs) / len(weekend_costs)
        self.assertGreater(avg_weekday, avg_weekend)

    def test_synthetic_data_persists_to_database(self):
        project = Project.objects.create(name='Synthetic DB Test')
        points = generate_project_timeseries(project.id, days=45, seed=99, persist=True)

        self.assertEqual(len(points), 45)
        self.assertEqual(CostDataPoint.objects.filter(project_id_str=project.id).count(), 45)

    def test_forecast_confidence_bounds_widen_over_time(self):
        project = Project.objects.create(name='Forecast Target')
        points = generate_project_timeseries(project.id, days=60, seed=42, persist=True)

        forecast = forecast_cost(points, horizon_days=30)
        self.assertEqual(len(forecast), 30)

        # Check bounds at day 1 vs day 15 vs day 30
        day_1 = forecast[0]
        day_15 = forecast[14]
        day_30 = forecast[29]

        spread_day_1 = day_1['upperBound'] - day_1['lowerBound']
        spread_day_15 = day_15['upperBound'] - day_15['lowerBound']
        spread_day_30 = day_30['upperBound'] - day_30['lowerBound']

        # Confidence bounds MUST strictly widen into the future
        self.assertGreater(spread_day_15, spread_day_1)
        self.assertGreater(spread_day_30, spread_day_15)

    def test_project_forecast_endpoint(self):
        project = Project.objects.create(name='Endpoint Project')

        response = self.client.get(f'/api/projects/{project.id}/forecast?horizonDays=30')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = response.json()
        self.assertTrue(data['success'])
        self.assertEqual(data['projectId'], project.id)
        self.assertEqual(len(data['forecast']), 30)
        self.assertIn('history', data)

    def test_project_anomalies_endpoint(self):
        project = Project.objects.create(name='Anomalies Project')

        response = self.client.get(f'/api/projects/{project.id}/anomalies')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = response.json()
        self.assertTrue(data['success'])
        self.assertEqual(data['projectId'], project.id)
        self.assertIn('anomalies', data)
