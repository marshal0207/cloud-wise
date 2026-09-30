from datetime import datetime, timezone
from decimal import Decimal
import json
import os

import boto3
from botocore.exceptions import BotoCoreError, ClientError, NoCredentialsError


class AwsPricingError(RuntimeError):
    pass


AWS_FALLBACK_HOURLY_RATES = {
    't3.micro': Decimal('0.0104'),
    't3.small': Decimal('0.0208'),
    't3.medium': Decimal('0.0416'),
    'c6i.large': Decimal('0.0850'),
    'c6i.xlarge': Decimal('0.1700'),
    'c6i.2xlarge': Decimal('0.3400'),
    'c6i.4xlarge': Decimal('0.6800'),
    'c6i.8xlarge': Decimal('1.3600'),
    'c6i.16xlarge': Decimal('2.7200'),
}


def get_closest_aws_instance(vcpu: int = 4, ram_gb: int = 16) -> str:
    """
    Match the closest standard AWS EC2 compute instance based on requested vCPU and RAM.
    """
    if vcpu <= 1:
        return 't3.small' if ram_gb > 1 else 't3.micro'
    if vcpu <= 2:
        return 'c6i.large'
    if vcpu <= 4:
        return 'c6i.xlarge'
    if vcpu <= 8:
        return 'c6i.2xlarge'
    if vcpu <= 16:
        return 'c6i.4xlarge'
    if vcpu <= 32:
        return 'c6i.8xlarge'
    return 'c6i.16xlarge'


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


def get_aws_price_snapshot(
    instance_type: str | None = None,
    region: str = 'Asia Pacific (Mumbai)',
    vcpu: int = 4,
    ram_gb: int = 16,
    storage_gb: int = 100,
    fallback_on_error: bool = False,
):
    resolved_instance = instance_type or get_closest_aws_instance(vcpu, ram_gb)
    usd_to_inr = Decimal(os.getenv('USD_TO_INR_RATE', '83'))
    source = 'AWS Pricing API'
    is_fallback = False

    try:
        hourly_usd = get_ec2_hourly_price(resolved_instance, region)
    except AwsPricingError:
        if not fallback_on_error:
            raise
        hourly_usd = AWS_FALLBACK_HOURLY_RATES.get(resolved_instance, Decimal('0.1700'))
        source = 'AWS Pricing (Estimated Fallback)'
        is_fallback = True
    except Exception as exc:
        if not fallback_on_error:
            raise AwsPricingError(str(exc)) from exc
        hourly_usd = AWS_FALLBACK_HOURLY_RATES.get(resolved_instance, Decimal('0.1700'))
        source = 'AWS Pricing (Estimated Fallback)'
        is_fallback = True

    monthly_usd = hourly_usd * Decimal('730')
    monthly_inr = monthly_usd * usd_to_inr

    return {
        'provider': 'AWS',
        'instanceType': resolved_instance,
        'region': region,
        'hourlyUsd': float(hourly_usd),
        'monthlyUsd': float(round(monthly_usd, 2)),
        'usdToInrRate': float(usd_to_inr),
        'monthlyInr': round(float(monthly_inr)),
        'source': source,
        'hoursPerMonth': 730,
        'specs': {
            'vcpu': vcpu,
            'ramGB': ram_gb,
            'storageGB': storage_gb,
            'instanceType': resolved_instance,
        },
        'estimated': is_fallback,
        'lastUpdated': datetime.now(timezone.utc).isoformat(),
    }