from datetime import datetime, timezone
from decimal import Decimal
import os
import requests


class AzurePricingError(RuntimeError):
    pass


AZURE_REGION_MAP = {
    'asia pacific (mumbai)': 'westindia',
    'gujarat (gift city / gandhinagar)': 'westindia',
    'mumbai': 'westindia',
    'west india': 'westindia',
    'westindia': 'westindia',
    'pune': 'centralindia',
    'central india': 'centralindia',
    'centralindia': 'centralindia',
    'chennai': 'southindia',
    'south india': 'southindia',
    'southindia': 'southindia',
    'us east': 'eastus',
    'eastus': 'eastus',
    'us west': 'westus2',
    'westus2': 'westus2',
    'europe': 'westeurope',
    'westeurope': 'westeurope',
}

AZURE_FALLBACK_HOURLY_RATES = {
    'Standard_B1s': Decimal('0.0104'),
    'Standard_B1ms': Decimal('0.0207'),
    'Standard_D2s_v5': Decimal('0.096'),
    'Standard_D4s_v5': Decimal('0.192'),
    'Standard_D8s_v5': Decimal('0.384'),
    'Standard_D16s_v5': Decimal('0.768'),
    'Standard_D32s_v5': Decimal('1.536'),
    'Standard_D64s_v5': Decimal('3.072'),
}


def get_closest_azure_sku(vcpu: int = 4, ram_gb: int = 16) -> str:
    """
    Match the closest standard Azure D-series or B-series SKU based on requested vCPU and RAM.
    Azure does not support arbitrary custom sizes, so we map to standard instances.
    """
    if vcpu <= 1:
        return 'Standard_B1ms' if ram_gb > 1 else 'Standard_B1s'
    if vcpu <= 2:
        return 'Standard_D2s_v5'
    if vcpu <= 4:
        return 'Standard_D4s_v5'
    if vcpu <= 8:
        return 'Standard_D8s_v5'
    if vcpu <= 16:
        return 'Standard_D16s_v5'
    if vcpu <= 32:
        return 'Standard_D32s_v5'
    return 'Standard_D64s_v5'


def get_azure_hourly_price(
    sku: str = 'Standard_D4s_v5',
    arm_region: str = 'westindia',
    timeout_seconds: int = 10,
) -> Decimal:
    """
    Query the public Azure Retail Prices API for the given VM SKU and region.
    Azure Retail Prices API is free, public, and unauthenticated.
    """
    api_url = 'https://prices.azure.com/api/retail/prices'
    filter_expr = (
        f"serviceName eq 'Virtual Machines' and "
        f"priceType eq 'Consumption' and "
        f"armRegionName eq '{arm_region}' and "
        f"armSkuName eq '{sku}' and "
        f"not contains(meterName, 'Spot') and "
        f"not contains(productName, 'Windows')"
    )

    try:
        response = requests.get(
            api_url,
            params={'$filter': filter_expr},
            timeout=timeout_seconds,
        )
        response.raise_for_status()
        data = response.json()
    except (requests.RequestException, ValueError) as exc:
        raise AzurePricingError(f'Azure Retail Prices API request failed: {exc}') from exc

    items = data.get('Items', [])
    for item in items:
        # Standard On-Demand Linux price
        retail_price = item.get('retailPrice')
        unit_of_measure = str(item.get('unitOfMeasure', '')).lower()
        if retail_price is not None and ('1 hour' in unit_of_measure or 'hour' in unit_of_measure):
            return Decimal(str(retail_price))

    # If exact item filter didn't match the meterName condition, fallback to any item with retailPrice > 0
    for item in items:
        retail_price = item.get('retailPrice')
        if retail_price and Decimal(str(retail_price)) > 0:
            return Decimal(str(retail_price))

    raise AzurePricingError(f'No Azure retail price found for {sku} in {arm_region}.')


def get_azure_price_snapshot(
    vcpu: int = 4,
    ram_gb: int = 16,
    storage_gb: int = 100,
    region: str = 'Asia Pacific (Mumbai)',
    sku: str | None = None,
) -> dict:
    """
    Fetch an Azure price snapshot matching the requested workload specification.
    Normalizes the output into the standard CloudWise pricing snapshot shape.
    """
    resolved_sku = sku or get_closest_azure_sku(vcpu, ram_gb)
    norm_region = region.strip().lower()
    arm_region = AZURE_REGION_MAP.get(norm_region, 'westindia')

    usd_to_inr = Decimal(os.getenv('USD_TO_INR_RATE', '83'))
    source = 'Azure Retail Prices API'
    is_fallback = False

    try:
        hourly_usd = get_azure_hourly_price(resolved_sku, arm_region)
    except Exception:
        # Graceful fallback to curated regional rate if external API is unreachable
        hourly_usd = AZURE_FALLBACK_HOURLY_RATES.get(resolved_sku, Decimal('0.192'))
        source = 'Azure Pricing (Estimated Fallback)'
        is_fallback = True

    monthly_usd = hourly_usd * Decimal('730')
    monthly_inr = monthly_usd * usd_to_inr

    return {
        'provider': 'Azure',
        'instanceType': resolved_sku,
        'region': region,
        'armRegion': arm_region,
        'hourlyUsd': float(hourly_usd),
        'monthlyUsd': float(monthly_usd),
        'usdToInrRate': float(usd_to_inr),
        'monthlyInr': round(float(monthly_inr)),
        'source': source,
        'hoursPerMonth': 730,
        'specs': {
            'vcpu': vcpu,
            'ramGB': ram_gb,
            'storageGB': storage_gb,
            'sku': resolved_sku,
        },
        'estimated': is_fallback,
        'lastUpdated': datetime.now(timezone.utc).isoformat(),
    }
