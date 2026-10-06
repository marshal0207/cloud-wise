from datetime import datetime, timezone
import json
import logging
import urllib.error
import urllib.parse
import urllib.request

logger = logging.getLogger(__name__)


class AzurePricingError(RuntimeError):
    pass


AZURE_VM_SPECS = {
    'Standard_B1s': {'vcpu': 1, 'memoryGiB': 1.0, 'storageType': 'Remote SSD'},
    'Standard_B2s': {'vcpu': 2, 'memoryGiB': 4.0, 'storageType': 'Remote SSD'},
    'Standard_D2s_v5': {'vcpu': 2, 'memoryGiB': 8.0, 'storageType': 'Remote SSD'},
    'Standard_D4s_v5': {'vcpu': 4, 'memoryGiB': 16.0, 'storageType': 'Remote SSD'},
    'Standard_D8s_v5': {'vcpu': 8, 'memoryGiB': 32.0, 'storageType': 'Remote SSD'},
    'Standard_E2s_v5': {'vcpu': 2, 'memoryGiB': 16.0, 'storageType': 'Remote SSD'},
    'Standard_E4s_v5': {'vcpu': 4, 'memoryGiB': 32.0, 'storageType': 'Remote SSD'},
}

AZURE_CURATED_SIZES = list(AZURE_VM_SPECS.keys())
AZURE_RETAIL_PRICES_API_URL = 'https://prices.azure.com/api/retail/prices'


def _fetch_azure_page(url):
    req = urllib.request.Request(
        url,
        headers={
            'Accept': 'application/json',
            'User-Agent': 'CloudWise-PricingService/1.0',
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as response:
            return json.loads(response.read().decode('utf-8'))
    except urllib.error.HTTPError as exc:
        raise AzurePricingError(f"Azure Pricing API HTTP {exc.code}: {exc.reason}") from exc
    except Exception as exc:
        raise AzurePricingError(f"Azure Pricing API request failed: {exc}") from exc


def fetch_price_catalog(region='centralindia'):
    """
    Fetches retail prices for curated Azure Virtual Machine sizes in Central India.
    Filters out Spot, Low Priority, and Windows offerings to retrieve standard Linux consumption pricing.
    """
    filter_query = (
        f"armRegionName eq '{region}' and priceType eq 'Consumption' and serviceName eq 'Virtual Machines'"
    )
    encoded_url = f"{AZURE_RETAIL_PRICES_API_URL}?$filter={urllib.parse.quote(filter_query)}"

    found_skus = {}
    current_url = encoded_url
    max_pages = 8
    page_count = 0

    try:
        while current_url and page_count < max_pages and len(found_skus) < len(AZURE_CURATED_SIZES):
            page_count += 1
            data = _fetch_azure_page(current_url)
            items = data.get('Items', [])

            for item in items:
                arm_sku = item.get('armSkuName') or item.get('skuName')
                if arm_sku not in AZURE_CURATED_SIZES:
                    continue

                meter_name = item.get('meterName', '')
                product_name = item.get('productName', '')

                # Exclude Spot, Low Priority, and Windows licenses
                if 'Spot' in meter_name or 'Low Priority' in meter_name:
                    continue
                if 'Windows' in product_name:
                    continue

                retail_price = item.get('retailPrice')
                if retail_price is None or retail_price <= 0:
                    continue

                # If we haven't stored it or this is a cheaper standard rate
                if arm_sku not in found_skus or retail_price < found_skus[arm_sku]['pricePerUnit']:
                    specs = AZURE_VM_SPECS[arm_sku]
                    unit = item.get('unitOfMeasure', '1 Hour')
                    if 'Hour' in unit:
                        unit = 'Hrs'

                    found_skus[arm_sku] = {
                        'provider': 'Azure',
                        'service': 'Virtual Machines',
                        'region': region,
                        'sku': item.get('skuId') or item.get('meterId') or f"azure-vm-{arm_sku}",
                        'instanceType': arm_sku,
                        'vcpu': specs['vcpu'],
                        'memoryGiB': float(specs['memoryGiB']),
                        'storageType': specs.get('storageType', 'Remote SSD'),
                        'unit': unit,
                        'pricePerUnit': float(retail_price),
                        'currency': item.get('currencyCode', 'USD'),
                        'pricingModel': 'Consumption',
                        'fetchedAt': datetime.now(timezone.utc),
                    }

            current_url = data.get('NextPageLink')
    except (AzurePricingError, urllib.error.HTTPError, Exception) as exc:
        logger.error("Azure Pricing API request failed: %s. Returning empty catalog.", exc)
        return []

    if not found_skus:
        logger.warning("No curated Azure VM prices found in region %s", region)

    return list(found_skus.values())
