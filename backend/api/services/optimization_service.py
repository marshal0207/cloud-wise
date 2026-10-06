import math


def evaluate_cpu_underutilization(metrics, baseline_monthly_cost=100.0):
    if len(metrics) >= 7 and all(m.get('cpu_percent', 100.0) < 20.0 for m in metrics[-7:]):
        return {
            'type': 'DOWNSIZE_INSTANCE',
            'category': 'Compute',
            'severity': 'HIGH',
            'estimatedSavingsUsd': baseline_monthly_cost * 0.5,
            'description': 'CPU utilization under 20% for 7 consecutive days',
        }
    return None


def evaluate_cpu_overutilization(metrics):
    if len(metrics) >= 3 and all(m.get('cpu_percent', 0.0) > 85.0 for m in metrics[-3:]):
        return {
            'type': 'UPSIZE_INSTANCE',
            'severity': 'HIGH',
            'estimatedSavingsUsd': 0.0,
            'description': 'CPU utilization exceeded 85% for 3 consecutive days',
        }
    return None


def evaluate_storage_underutilization(storage_percent, provisioned_gb):
    if storage_percent < 30.0 and provisioned_gb > 100.0:
        return {
            'type': 'REDUCE_STORAGE',
            'category': 'Storage',
            'severity': 'MEDIUM',
            'estimatedSavingsUsd': 20.0,
            'description': 'Storage utilization under 30% on large volume',
        }
    return None


def evaluate_idle_workload(metrics, current_monthly_cost=80.0):
    if len(metrics) >= 14 and all(
        m.get('cpu_percent', 100.0) < 5.0 and m.get('requests_count', 100) < 10
        for m in metrics[-14:]
    ):
        return {
            'type': 'SHUTDOWN_IDLE',
            'category': 'Reservation',
            'severity': 'HIGH',
            'estimatedSavingsUsd': current_monthly_cost,
            'description': 'Workload is idle',
        }
    return None


def detect_cost_anomalies(history, threshold_z=3.0):
    if not history:
        return []
    costs = [
        item.get('costUsd', item.get('cost', 0))
        if isinstance(item, dict)
        else getattr(item, 'cost_usd', 0)
        for item in history
    ]
    if len(costs) < 2:
        return []
    mean = sum(costs) / len(costs)
    variance = sum((cost - mean) ** 2 for cost in costs) / len(costs)
    stddev = math.sqrt(variance) if variance > 0 else 1.0
    anomalies = []
    for item in history:
        cost = (
            item.get('costUsd', item.get('cost', 0))
            if isinstance(item, dict)
            else getattr(item, 'cost_usd', 0)
        )
        z_score = (cost - mean) / stddev
        if z_score > threshold_z:
            anomalies.append({
                'date': item.get('date') if isinstance(item, dict) else str(getattr(item, 'date', '')),
                'cost': cost,
                'zScore': z_score,
                'severity': 'CRITICAL',
                'expectedRange': [max(0, mean - stddev), mean + stddev],
            })
    return anomalies


def generate_optimization_suggestions(project_id, custom_metrics=None):
    if not custom_metrics:
        custom_metrics = [{'cpu_percent': 15.0, 'requests_count': 500} for _ in range(7)]
    suggestion = evaluate_cpu_underutilization(custom_metrics)
    return {'suggestions': [suggestion] if suggestion else []}