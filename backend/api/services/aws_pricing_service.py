from decimal import Decimal
import json
import os

import boto3
from botocore.exceptions import BotoCoreError, ClientError, NoCredentialsError


class AwsPricingError(RuntimeError):
    pass


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
    return {
        'provider': 'AWS',
        'instanceType': instance_type,
        'region': region,
        'hourlyUsd': float(hourly_usd),
        'monthlyUsd': float(monthly_usd),
        'usdToInrRate': float(usd_to_inr),
        'monthlyInr': round(float(monthly_inr)),
        'source': 'AWS Pricing API',
        'hoursPerMonth': 730,
    }