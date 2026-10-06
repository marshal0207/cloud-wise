from datetime import datetime, timezone
import json
import logging
import os
import urllib.error
import urllib.parse
import urllib.request

logger = logging.getLogger(__name__)


class GcpPricingError(RuntimeError):
    pass


GCP_MACHINE_SPECS = {
    'e2-micro': {'vcpu': 2, 'memoryGiB': 1.0, 'storageType': 'Persistent Disk', 'default_hourly': 0.0084},
    'e2-small': {'vcpu': 2, 'memoryGiB': 2.0, 'storageType': 'Persistent Disk', 'default_hourly': 0.0168},
    'e2-medium': {'vcpu': 2, 'memoryGiB': 4.0, 'storageType': 'Persistent Disk', 'default_hourly': 0.0336},
    'e2-standard-2': {'vcpu': 2, 'memoryGiB': 8.0, 'storageType': 'Persistent Disk', 'default_hourly': 0.0672},
    'e2-standard-4': {'vcpu': 4, 'memoryGiB': 16.0, 'storageType': 'Persistent Disk', 'default_hourly': 0.1344},
    'n2-standard-2': {'vcpu': 2, 'memoryGiB': 8.0, 'storageType': 'Persistent Disk', 'default_hourly': 0.0970},
    'n2-standard-4': {'vcpu': 4, 'memoryGiB': 16.0, 'storageType': 'Persistent Disk', 'default_hourly': 0.1940},
}

GCP_CURATED_MACHINES = list(GCP_MACHINE_SPECS.keys())
GCP_COMPUTE_SERVICE_ID = '6F81-5844-456A'
GCP_BILLING_BASE_URL = f'https://cloudbilling.googleapis.com/v1/services/{GCP_COMPUTE_SERVICE_ID}/skus'


def _extract_unit_price(pricing_info):
    if not pricing_info:
        return 0.0
    for info in pricing_info:
        expression = info.get('pricingExpression', {})
        for rate in expression.get('tieredRates', []):
            price = rate.get('unitPrice', {})
            units = int(price.get('units', 0))
            nanos = int(price.get('nanos', 0))
            return units + (nanos / 1e9)
    return 0.0


def fetch_price_catalog(region='asia-south1'):
    """
    Fetches curated GCP Compute Engine instance prices for asia-south1.
    Degrades gracefully (log + skip) if GCP_BILLING_API_KEY is missing or invalid.
    """
    api_key = os.getenv('GCP_BILLING_API_KEY')
    if not api_key:
        logger.warning("GCP_BILLING_API_KEY is not set. Skipping GCP pricing catalog fetch.")
        return []

    url = f"{GCP_BILLING_BASE_URL}?key={urllib.parse.quote(api_key)}"
    skus_by_description = {}
    next_page_token = None
    page_count = 0
    max_pages = 5

    try:
        while page_count < max_pages:
            page_count += 1
            request_url = f"{url}&pageToken={next_page_token}" if next_page_token else url
            req = urllib.request.Request(
                request_url,
                headers={'Accept': 'application/json', 'User-Agent': 'CloudWise-PricingService/1.0'},
            )
            with urllib.request.urlopen(req, timeout=15) as response:
                payload = json.loads(response.read().decode('utf-8'))

            for sku in payload.get('skus', []):
                regions = sku.get('serviceRegions', [])
                if region in regions or 'global' in regions:
                    desc = sku.get('description', '')
                    price = _extract_unit_price(sku.get('pricingInfo', []))
                    if price > 0:
                        skus_by_description[desc] = {
                            'skuId': sku.get('skuId'),
                            'price': price,
                        }

            next_page_token = payload.get('nextPageToken')
            if not next_page_token:
                break

    except urllib.error.HTTPError as exc:
        logger.error("GCP Billing API HTTP error %s (%s). Skipping GCP catalog.", exc.code, exc.reason)
        return []
    except Exception as exc:
        logger.error("GCP Billing API request failed: %s. Skipping GCP catalog.", exc)
        return []

    # Calculate prices from retrieved SKUs or instance type rate
    e2_core_rate = None
    e2_ram_rate = None
    n2_core_rate = None
    n2_ram_rate = None

    for desc, info in skus_by_description.items():
        desc_lower = desc.lower()
        if 'e2 instance core' in desc_lower:
            e2_core_rate = info['price']
        elif 'e2 instance ram' in desc_lower:
            e2_ram_rate = info['price']
        elif 'n2 instance core' in desc_lower:
            n2_core_rate = info['price']
        elif 'n2 instance ram' in desc_lower:
            n2_ram_rate = info['price']

    catalog = []
    now = datetime.now(timezone.utc)

    for machine_type in GCP_CURATED_MACHINES:
        specs = GCP_MACHINE_SPECS[machine_type]
        calculated_price = None

        if machine_type.startswith('e2-standard') and e2_core_rate and e2_ram_rate:
            calculated_price = (specs['vcpu'] * e2_core_rate) + (specs['memoryGiB'] * e2_ram_rate)
        elif machine_type.startswith('n2-standard') and n2_core_rate and n2_ram_rate:
            calculated_price = (specs['vcpu'] * n2_core_rate) + (specs['memoryGiB'] * n2_ram_rate)
        elif specs.get('default_hourly'):
            calculated_price = specs['default_hourly']

        if calculated_price is not None:
            catalog.append({
                'provider': 'GCP',
                'service': 'Compute Engine',
                'region': region,
                'sku': f"gcp-compute-{machine_type}-{region}",
                'instanceType': machine_type,
                'vcpu': specs['vcpu'],
                'memoryGiB': float(specs['memoryGiB']),
                'storageType': specs.get('storageType', 'Persistent Disk'),
                'unit': 'Hrs',
                'pricePerUnit': round(float(calculated_price), 4),
                'currency': 'USD',
                'pricingModel': 'OnDemand',
                'fetchedAt': now,
            })

    return catalog
