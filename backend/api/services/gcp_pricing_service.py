from datetime import datetime, timezone
from decimal import Decimal
import os
import requests

from .pricing_common import get_usd_to_inr_rate


class GcpPricingError(RuntimeError):
    pass


GCP_REGION_MAP = {
    'asia pacific (mumbai)': 'asia-south1',
    'gujarat (gift city / gandhinagar)': 'asia-south1',
    'mumbai': 'asia-south1',
    'delhi': 'asia-south2',
    'us central': 'us-central1',
    'us-central1': 'us-central1',
    'us east': 'us-east1',
    'us-east1': 'us-east1',
    'europe west': 'europe-west1',
    'europe-west1': 'europe-west1',
}

# Baseline hourly rates for E2 Custom Machine Types in asia-south1 (Mumbai)
GCP_FALLBACK_E2_RATES = {
    'asia-south1': {
        'vcpu_hourly': Decimal('0.023797'),
        'ram_gb_hourly': Decimal('0.003189'),
    },
    'default': {
        'vcpu_hourly': Decimal('0.022890'),
        'ram_gb_hourly': Decimal('0.003067'),
    },
}


def build_gcp_custom_machine_type(vcpu: int = 4, ram_gb: int = 16) -> str:
    """Format GCP custom machine type string, e.g. e2-custom-4-16384."""
    ram_mb = int(ram_gb * 1024)
    return f'e2-custom-{vcpu}-{ram_mb}'


def fetch_gcp_rates_from_catalog(api_key: str, gcp_region: str, timeout_seconds: int = 10) -> tuple[Decimal, Decimal]:
    """
    Query the Google Cloud Billing Catalog API for Compute Engine E2 vCPU and RAM rates.
    Service ID 6F81-5844-456A represents Compute Engine.
    """
    api_url = f'https://cloudbilling.googleapis.com/v1/services/6F81-5844-456A/skus'
    response = requests.get(
        api_url,
        params={'key': api_key},
        timeout=timeout_seconds,
    )
    response.raise_for_status()
    data = response.json()

    vcpu_rate = None
    ram_rate = None

    for sku in data.get('skus', []):
        description = sku.get('description', '')
        service_regions = sku.get('serviceRegions', [])
        if gcp_region not in service_regions:
            continue

        pricing_info = sku.get('pricingInfo', [])
        if not pricing_info:
            continue
        tiers = pricing_info[0].get('pricingExpression', {}).get('tieredRates', [])
        if not tiers:
            continue
        unit_price = tiers[0].get('unitPrice', {})
        nanos = Decimal(unit_price.get('nanos', 0))
        units = Decimal(unit_price.get('units', 0))
        rate = units + (nanos / Decimal('1000000000'))

        if 'E2 Instance Core' in description and vcpu_rate is None:
            vcpu_rate = rate
        elif 'E2 Instance Ram' in description and ram_rate is None:
            ram_rate = rate

        if vcpu_rate is not None and ram_rate is not None:
            break

    if vcpu_rate is None or ram_rate is None:
        raise GcpPricingError(f'Could not find E2 rates for region {gcp_region} in catalog.')

    return vcpu_rate, ram_rate


def get_gcp_price_snapshot(
    vcpu: int = 4,
    ram_gb: int = 16,
    storage_gb: int = 100,
    region: str = 'Asia Pacific (Mumbai)',
) -> dict:
    """
    Fetch a GCP price snapshot for a custom machine type matching the exact requested vCPU and RAM.
    If GCP_API_KEY is configured, queries the Cloud Billing Catalog API.
    If GCP_API_KEY is absent or query fails, returns a curated fallback snapshot with an estimated flag.
    """
    machine_type = build_gcp_custom_machine_type(vcpu, ram_gb)
    norm_region = region.strip().lower()
    gcp_region = GCP_REGION_MAP.get(norm_region, 'asia-south1')

    api_key = os.getenv('GCP_API_KEY', '').strip()
    usd_to_inr = get_usd_to_inr_rate()
    source = 'GCP Cloud Billing Catalog API'
    is_fallback = False

    if api_key:
        try:
            vcpu_rate, ram_rate = fetch_gcp_rates_from_catalog(api_key, gcp_region)
        except Exception:
            fallback_cfg = GCP_FALLBACK_E2_RATES.get(gcp_region, GCP_FALLBACK_E2_RATES['default'])
            vcpu_rate = fallback_cfg['vcpu_hourly']
            ram_rate = fallback_cfg['ram_gb_hourly']
            source = 'GCP Pricing (Estimated Fallback)'
            is_fallback = True
    else:
        fallback_cfg = GCP_FALLBACK_E2_RATES.get(gcp_region, GCP_FALLBACK_E2_RATES['default'])
        vcpu_rate = fallback_cfg['vcpu_hourly']
        ram_rate = fallback_cfg['ram_gb_hourly']
        source = 'GCP Pricing (Estimated Fallback)'
        is_fallback = True

    hourly_usd = (Decimal(vcpu) * vcpu_rate) + (Decimal(ram_gb) * ram_rate)
    monthly_usd = hourly_usd * Decimal('730')
    monthly_inr = monthly_usd * usd_to_inr

    return {
        'provider': 'GCP',
        'instanceType': machine_type,
        'region': region,
        'gcpRegion': gcp_region,
        'hourlyUsd': float(round(hourly_usd, 4)),
        'monthlyUsd': float(round(monthly_usd, 2)),
        'usdToInrRate': float(usd_to_inr),
        'monthlyInr': round(float(monthly_inr)),
        'source': source,
        'hoursPerMonth': 730,
        'specs': {
            'vcpu': vcpu,
            'ramGB': ram_gb,
            'storageGB': storage_gb,
            'machineType': machine_type,
            'vcpuHourlyUsd': float(vcpu_rate),
            'ramGbHourlyUsd': float(ram_rate),
        },
        'estimated': is_fallback,
        'lastUpdated': datetime.now(timezone.utc).isoformat(),
    }
