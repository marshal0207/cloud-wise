from datetime import datetime, timezone
from decimal import Decimal
import json
import logging
import os

import boto3
from botocore.exceptions import BotoCoreError, ClientError, NoCredentialsError

logger = logging.getLogger(__name__)


class AwsPricingError(RuntimeError):
    pass


AWS_INSTANCE_SPECS = {
    't3.micro': {'vcpu': 2, 'memoryGiB': 1.0, 'storageType': 'EBS only'},
    't3.small': {'vcpu': 2, 'memoryGiB': 2.0, 'storageType': 'EBS only'},
    't3.medium': {'vcpu': 2, 'memoryGiB': 4.0, 'storageType': 'EBS only'},
    't3.large': {'vcpu': 2, 'memoryGiB': 8.0, 'storageType': 'EBS only'},
    'c6i.large': {'vcpu': 2, 'memoryGiB': 4.0, 'storageType': 'EBS only'},
    'c6i.xlarge': {'vcpu': 4, 'memoryGiB': 8.0, 'storageType': 'EBS only'},
    'm6i.large': {'vcpu': 2, 'memoryGiB': 8.0, 'storageType': 'EBS only'},
    'm6i.xlarge': {'vcpu': 4, 'memoryGiB': 16.0, 'storageType': 'EBS only'},
    'r6i.large': {'vcpu': 2, 'memoryGiB': 16.0, 'storageType': 'EBS only'},
    'r6i.xlarge': {'vcpu': 4, 'memoryGiB': 32.0, 'storageType': 'EBS only'},
}

AWS_CURATED_INSTANCES = list(AWS_INSTANCE_SPECS.keys())


def get_ec2_hourly_price(instance_type='c6i.xlarge', region='Asia Pacific (Mumbai)'):
    try:
        client = boto3.client(
            'pricing',
            region_name=os.getenv('AWS_PRICING_API_REGION', 'us-east-1'),
        )
        response = client.get_products(
            ServiceCode='AmazonEC2',
            Filters=[
                {'Type': 'TERM_MATCH', 'Field': 'instanceType', 'Value': instance_type},
                {'Type': 'TERM_MATCH', 'Field': 'location', 'Value': region},
                {'Type': 'TERM_MATCH', 'Field': 'operatingSystem', 'Value': 'Linux'},
                {'Type': 'TERM_MATCH', 'Field': 'preInstalledSw', 'Value': 'NA'},
                {'Type': 'TERM_MATCH', 'Field': 'tenancy', 'Value': 'Shared'},
                {'Type': 'TERM_MATCH', 'Field': 'capacitystatus', 'Value': 'Used'},
            ],
            MaxResults=20,
        )
    except (BotoCoreError, ClientError, NoCredentialsError) as exc:
        raise AwsPricingError(f'AWS Pricing API request failed: {exc}') from exc

    for raw_product in response.get('PriceList', []):
        product = json.loads(raw_product) if isinstance(raw_product, str) else raw_product
        terms = product.get('terms', {}).get('OnDemand', {})
        for term in terms.values():
            for dimension in term.get('priceDimensions', {}).values():
                price = dimension.get('pricePerUnit', {}).get('USD')
                if price:
                    return Decimal(price)

    raise AwsPricingError(f'No AWS EC2 price found for {instance_type} in {region}.')


def get_aws_price_snapshot(instance_type='c6i.xlarge', region='Asia Pacific (Mumbai)'):
    hourly_usd = get_ec2_hourly_price(instance_type, region)
    usd_to_inr = Decimal(os.getenv('USD_TO_INR_RATE', '83'))
    monthly_usd = hourly_usd * Decimal('730')
    monthly_inr = monthly_usd * usd_to_inr
    specs = AWS_INSTANCE_SPECS.get(instance_type, {'vcpu': 2, 'memoryGiB': 4.0, 'storageType': 'EBS only'})

    return {
        'provider': 'AWS',
        'service': 'EC2',
        'region': region,
        'sku': f'aws-ec2-{instance_type}-{region.lower().replace(" ", "-")}',
        'instanceType': instance_type,
        'vcpu': specs['vcpu'],
        'memoryGiB': float(specs['memoryGiB']),
        'storageType': specs.get('storageType', 'EBS only'),
        'unit': 'Hrs',
        'pricePerUnit': float(hourly_usd),
        'currency': 'USD',
        'pricingModel': 'OnDemand',
        'fetchedAt': datetime.now(timezone.utc),
        # Legacy/display helper fields preserved for existing API consumers
        'hourlyUsd': float(hourly_usd),
        'monthlyUsd': float(monthly_usd),
        'usdToInrRate': float(usd_to_inr),
        'monthlyInr': round(float(monthly_inr)),
        'source': 'AWS Pricing API',
        'hoursPerMonth': 730,
    }


def fetch_price_catalog(region='Asia Pacific (Mumbai)'):
    catalog = []
    try:
        for instance_type in AWS_CURATED_INSTANCES:
            try:
                snapshot = get_aws_price_snapshot(instance_type=instance_type, region=region)
                catalog.append(snapshot)
            except AwsPricingError as exc:
                logger.warning("Failed to fetch AWS price for %s: %s", instance_type, exc)
                continue
    except Exception as exc:
        logger.error("AWS pricing catalog fetch failed: %s. Returning empty catalog.", exc)
        return []

    if not catalog:
        logger.warning("No AWS EC2 prices could be fetched (credentials missing or API error). Returning empty catalog.")
    return catalog