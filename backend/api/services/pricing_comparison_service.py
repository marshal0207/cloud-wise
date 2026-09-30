"""
pricing_comparison_service — Unified 3-cloud pricing comparison engine (AWS, Azure, GCP).

Matching Rules:
1. Exact Tier Match:
   If requested vCPU and RAM exactly equal a cached representative tier,
   serve that tier with match_type = 'EXACT_TIER'.
2. Closest Match (within 20%):
   If requested vCPU AND RAM are both within 20% of a cached tier,
   serve that cached tier labeled match_type = 'CLOSEST_MATCH'.
3. On-Demand Live Lookup:
   If outside 20% of all tiers (or exceeding Tier 5, e.g. 32vCPU/128GB),
   perform a live query for the exact requested spec, cache the result
   in CloudPricingCache, and serve with match_type = 'ON_DEMAND_LOOKUP'.
"""

from decimal import Decimal
from typing import Any

from api.models import CloudPricingCache
from api.services.aws_pricing_service import (
    get_aws_price_snapshot,
    get_closest_aws_instance,
)
from api.services.azure_pricing_service import (
    get_azure_price_snapshot,
    get_closest_azure_sku,
)
from api.services.gcp_pricing_service import (
    build_gcp_custom_machine_type,
    get_gcp_price_snapshot,
)
from api.services.pricing_common import get_usd_to_inr_rate

from api.management.commands.refresh_pricing import REPRESENTATIVE_SPEC_TIERS


def find_matching_spec_tier(vcpu: int, ram_gb: int) -> tuple[str, dict[str, Any] | None]:
    """
    Evaluate requested vCPU and RAM against cached representative tiers.
    Returns (match_type, matched_tier_dict or None).
    match_type is one of: 'EXACT_TIER', 'CLOSEST_MATCH', 'ON_DEMAND_LOOKUP'.
    """
    # 1. Exact match
    for tier in REPRESENTATIVE_SPEC_TIERS:
        if tier['vcpu'] == vcpu and tier['ram_gb'] == ram_gb:
            return 'EXACT_TIER', tier

    # 2. Closest match within 20% on both vCPU and RAM
    best_candidate = None
    min_combined_diff = 1.0

    for tier in REPRESENTATIVE_SPEC_TIERS:
        vcpu_diff = abs(vcpu - tier['vcpu']) / tier['vcpu']
        ram_diff = abs(ram_gb - tier['ram_gb']) / tier['ram_gb']

        if vcpu_diff <= 0.20 and ram_diff <= 0.20:
            combined = vcpu_diff + ram_diff
            if combined < min_combined_diff:
                min_combined_diff = combined
                best_candidate = tier

    if best_candidate is not None:
        return 'CLOSEST_MATCH', best_candidate

    # 3. Beyond 20% or > Tier 5 -> on-demand lookup
    return 'ON_DEMAND_LOOKUP', None


def get_or_fetch_provider_pricing(
    provider: str,
    instance_type: str,
    region: str,
    vcpu: int,
    ram_gb: int,
    storage_gb: int,
    match_type: str,
    matched_tier_name: str | None,
) -> dict[str, Any]:
    """
    Retrieve pricing from CloudPricingCache or trigger a live fetch if missing / on-demand.
    """
    cached = CloudPricingCache.objects.filter(
        provider=provider,
        instance_type=instance_type,
        region=region,
    ).first()

    if cached and match_type in ('EXACT_TIER', 'CLOSEST_MATCH'):
        is_estimated = getattr(cached, 'estimated', None)
        if is_estimated is None:
            is_estimated = cached.specs.get('estimated', 'Estimated' in (cached.source or ''))
        return {
            'provider': provider,
            'instanceType': cached.instance_type,
            'region': cached.region,
            'monthlyInr': float(cached.price_per_month),
            'hourlyUsd': float(cached.hourly_usd),
            'source': f'CloudPricingCache ({cached.source})',
            'matchType': match_type,
            'matchedTier': matched_tier_name,
            'specs': cached.specs,
            'lastUpdated': cached.last_updated.isoformat(),
            'estimated': bool(is_estimated),
        }

    # Fetch live
    if provider == 'AWS':
        snapshot = get_aws_price_snapshot(
            instance_type=instance_type,
            region=region,
            vcpu=vcpu,
            ram_gb=ram_gb,
            storage_gb=storage_gb,
            fallback_on_error=True,
        )
    elif provider == 'Azure':
        snapshot = get_azure_price_snapshot(
            vcpu=vcpu,
            ram_gb=ram_gb,
            storage_gb=storage_gb,
            region=region,
            sku=instance_type,
        )
    elif provider == 'GCP':
        snapshot = get_gcp_price_snapshot(
            vcpu=vcpu,
            ram_gb=ram_gb,
            storage_gb=storage_gb,
            region=region,
        )
    else:
        raise ValueError(f"Unknown provider '{provider}'")

    monthly_inr = Decimal(str(snapshot.get('monthlyInr', 0)))
    hourly_usd = Decimal(str(snapshot.get('hourlyUsd', 0.0)))
    source = snapshot.get('source', 'API')
    specs = snapshot.get('specs', {})
    is_estimated = bool(snapshot.get('estimated', False))

    # Upsert into cache
    cache_entry, _ = CloudPricingCache.objects.update_or_create(
        provider=provider,
        instance_type=instance_type,
        region=region,
        defaults={
            'price_per_month': monthly_inr,
            'hourly_usd': hourly_usd,
            'specs': specs,
            'source': source,
            'estimated': is_estimated,
        },
    )

    return {
        'provider': provider,
        'instanceType': instance_type,
        'region': region,
        'monthlyInr': float(monthly_inr),
        'hourlyUsd': float(hourly_usd),
        'source': source,
        'matchType': match_type,
        'matchedTier': matched_tier_name,
        'specs': specs,
        'lastUpdated': cache_entry.last_updated.isoformat(),
        'estimated': is_estimated,
    }


def compare_cloud_pricing(
    vcpu: int = 4,
    ram_gb: int = 16,
    storage_gb: int = 100,
    region: str = 'Asia Pacific (Mumbai)',
) -> dict[str, Any]:
    """
    Compare AWS, Azure, and GCP pricing for the requested compute specification.
    """
    match_type, matched_tier = find_matching_spec_tier(vcpu, ram_gb)
    matched_tier_name = matched_tier['tier'] if matched_tier else None

    # Determine instance types per provider
    if match_type in ('EXACT_TIER', 'CLOSEST_MATCH') and matched_tier:
        aws_instance = matched_tier['aws_instance']
        azure_sku = matched_tier['azure_sku']
        gcp_type = matched_tier['gcp_type']
        target_vcpu = matched_tier['vcpu']
        target_ram = matched_tier['ram_gb']
    else:
        # On-demand lookup uses exact requested specs
        aws_instance = get_closest_aws_instance(vcpu, ram_gb)
        azure_sku = get_closest_azure_sku(vcpu, ram_gb)
        gcp_type = build_gcp_custom_machine_type(vcpu, ram_gb)
        target_vcpu = vcpu
        target_ram = ram_gb

    usd_to_inr = get_usd_to_inr_rate()

    aws_data = get_or_fetch_provider_pricing(
        provider='AWS',
        instance_type=aws_instance,
        region=region,
        vcpu=target_vcpu,
        ram_gb=target_ram,
        storage_gb=storage_gb,
        match_type=match_type,
        matched_tier_name=matched_tier_name,
    )

    azure_data = get_or_fetch_provider_pricing(
        provider='Azure',
        instance_type=azure_sku,
        region=region,
        vcpu=target_vcpu,
        ram_gb=target_ram,
        storage_gb=storage_gb,
        match_type=match_type,
        matched_tier_name=matched_tier_name,
    )

    gcp_data = get_or_fetch_provider_pricing(
        provider='GCP',
        instance_type=gcp_type,
        region=region,
        vcpu=target_vcpu,
        ram_gb=target_ram,
        storage_gb=storage_gb,
        match_type=match_type,
        matched_tier_name=matched_tier_name,
    )

    return {
        'specs': {
            'vcpu': vcpu,
            'ramGB': ram_gb,
            'storageGB': storage_gb,
            'region': region,
        },
        'matchType': match_type,
        'matchedTier': matched_tier_name,
        'usdToInrRate': float(usd_to_inr),
        'providers': {
            'AWS': aws_data,
            'Azure': azure_data,
            'GCP': gcp_data,
        },
    }
