from datetime import timedelta


def forecast_cost(points, horizon_days=30):
    if not points:
        return []

    last_date = points[-1].date
    last_cost = points[-1].cost_usd
    forecast = []
    for i in range(1, horizon_days + 1):
        future_date = last_date + timedelta(days=i)
        spread = i * 2.0
        forecast.append({
            'date': str(future_date),
            'costUsd': last_cost,
            'lowerBound': max(0, last_cost - spread),
            'upperBound': last_cost + spread,
        })
    return forecast