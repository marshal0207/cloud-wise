from datetime import date, timedelta
import math
import random
from typing import List, Optional

from api.models import CostDataPoint, Project


def generate_project_timeseries(
    project_id: str,
    days: int = 90,
    seed: int = 42,
    base_daily_cost: float = 35.0,
    persist: bool = True,
    inject_anomaly: bool = False,
) -> List[CostDataPoint]:
    """
    Generates deterministic, realistic daily cost and telemetry time-series data for a project.
    Includes base cost, upward trend, weekly seasonality (lower weekend usage), and realistic noise.
    Optionally persists points to CostDataPoint model.
    """
    rng = random.Random(seed)
    today = date.today()
    start_date = today - timedelta(days=days - 1)

    project_instance = Project.objects.filter(pk=project_id).first()

    data_points = []
    created_or_updated = []

    for i in range(days):
        current_date = start_date + timedelta(days=i)
        weekday = current_date.weekday()  # 0=Monday, 6=Sunday

        # 1. Gentle upward trend (~15% growth over 90 days)
        trend_factor = 1.0 + (0.15 * (i / max(1, days)))

        # 2. Weekly seasonality: weekends have noticeably lower activity
        if weekday == 5:    # Saturday
            seasonality = 0.78
        elif weekday == 6:  # Sunday
            seasonality = 0.72
        elif weekday in (1, 2, 3):  # Tue-Thu peak mid-week
            seasonality = 1.06
        else:
            seasonality = 1.00

        # 3. Deterministic noise (+/- 6%)
        noise = 1.0 + rng.uniform(-0.06, 0.06)

        # Baseline cost calculation
        daily_cost = round(base_daily_cost * trend_factor * seasonality * noise, 2)

        # Inject anomaly on a specific day if requested
        if inject_anomaly and i == days - 5:
            daily_cost = round(daily_cost * 4.2, 2)  # 4x spike

        # Telemetry metrics correlated with workload
        base_cpu = 40.0 * seasonality * (daily_cost / max(1.0, base_daily_cost))
        cpu_percent = round(min(98.0, max(5.0, base_cpu + rng.uniform(-5.0, 5.0))), 1)

        base_ram = 50.0 + (10.0 * (i / max(1, days)))
        ram_percent = round(min(95.0, max(15.0, base_ram + rng.uniform(-3.0, 3.0))), 1)

        # Storage grows slowly and monotonically
        storage_percent = round(min(90.0, 20.0 + (15.0 * (i / max(1, days))) + rng.uniform(-0.5, 0.5)), 1)
        requests_count = int(daily_cost * 3200 + rng.randint(-1500, 1500))

        point = CostDataPoint(
            project=project_instance,
            project_id_str=project_id,
            date=current_date,
            cost_usd=daily_cost,
            cpu_percent=cpu_percent,
            ram_percent=ram_percent,
            storage_percent=storage_percent,
            requests_count=requests_count,
        )
        data_points.append(point)

    if persist:
        # Clear existing for project and bulk-create for high performance
        CostDataPoint.objects.filter(project_id_str=project_id).delete()
        CostDataPoint.objects.bulk_create(data_points)
        return list(CostDataPoint.objects.filter(project_id_str=project_id).order_by('date'))

    return data_points
