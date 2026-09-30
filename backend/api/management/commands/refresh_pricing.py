"""
refresh_pricing — Ingestion and cache command for multi-cloud pricing (AWS, Azure, GCP).

Scope & Architectural Decision on Representative Tiers vs High-Spec Requests:
------------------------------------------------------------------------------
This command caches a curated 5-tier baseline covering standard production presets.
The Estimation module sliders support specifications up to 64 vCPU and 256 GB RAM.

Architectural Rule for High-Spec Workloads (> Tier 5 or custom combinations):
- When Task C's unified endpoint (/api/pricing/compare) receives a request that exceeds
  Tier 5 (or has an arbitrary non-standard ratio), it does NOT quietly clip or return
  Tier 5's price as an exact match.
- Instead, the comparison layer falls through to an on-demand live query against the actual
  requested spec using:
    * AWS: dynamic compute mapping via get_closest_aws_instance (e.g. c6i.8xlarge, c6i.16xlarge)
    * Azure: dynamic SKU resolution via get_closest_azure_sku (e.g. Standard_D32s_v5, Standard_D64s_v5)
    * GCP: dynamic custom machine type via build_gcp_custom_machine_type (e.g. e2-custom-32-131072)
  The on-demand result is then cached on the fly for subsequent requests.
"""

from datetime import datetime, timedelta, timezone
from decimal import Decimal

from django.core.management.base import BaseCommand
from django.utils import timezone as dj_timezone

from api.models import CloudPricingCache
from api.services.aws_pricing_service import get_aws_price_snapshot
from api.services.azure_pricing_service import get_azure_price_snapshot
from api.services.gcp_pricing_service import get_gcp_price_snapshot


REPRESENTATIVE_SPEC_TIERS = [
    {
        'tier': 'Tier 1 (Starter / Dev)',
        'vcpu': 1,
        'ram_gb': 2,
        'storage_gb': 30,
        'aws_instance': 't3.small',
        'azure_sku': 'Standard_B1ms',
        'gcp_type': 'e2-custom-1-2048',
    },
    {
        'tier': 'Tier 2 (General / Web API)',
        'vcpu': 2,
        'ram_gb': 8,
        'storage_gb': 50,
        'aws_instance': 'c6i.large',
        'azure_sku': 'Standard_D2s_v5',
        'gcp_type': 'e2-custom-2-8192',
    },
    {
        'tier': 'Tier 3 (Production Baseline)',
        'vcpu': 4,
        'ram_gb': 16,
        'storage_gb': 100,
        'aws_instance': 'c6i.xlarge',
        'azure_sku': 'Standard_D4s_v5',
        'gcp_type': 'e2-custom-4-16384',
    },
    {
        'tier': 'Tier 4 (High Performance)',
        'vcpu': 8,
        'ram_gb': 32,
        'storage_gb': 250,
        'aws_instance': 'c6i.2xlarge',
        'azure_sku': 'Standard_D8s_v5',
        'gcp_type': 'e2-custom-8-32768',
    },
    {
        'tier': 'Tier 5 (Enterprise / Memory)',
        'vcpu': 16,
        'ram_gb': 64,
        'storage_gb': 500,
        'aws_instance': 'c6i.4xlarge',
        'azure_sku': 'Standard_D16s_v5',
        'gcp_type': 'e2-custom-16-65536',
    },
]


class Command(BaseCommand):
    help = 'Refresh and cache cloud pricing from AWS, Azure, and GCP for representative spec tiers.'

    def add_arguments(self, parser):
        parser.add_argument(
            '--force',
            action='store_true',
            help='Force re-fetching prices regardless of last_updated age.',
        )
        parser.add_argument(
            '--provider',
            type=str,
            default=None,
            help='Filter refresh to a single provider (AWS, Azure, or GCP).',
        )
        parser.add_argument(
            '--region',
            type=str,
            default='Asia Pacific (Mumbai)',
            help='Target region (default: Asia Pacific (Mumbai)).',
        )
        parser.add_argument(
            '--max-age-hours',
            type=int,
            default=24,
            help='Skip providers refreshed within this many hours (default: 24).',
        )

    def handle(self, *args, **options):
        force = options['force']
        target_provider = (options['provider'] or '').strip().upper()
        region = options['region']
        max_age_hours = options['max_age_hours']

        valid_providers = {'AWS', 'AZURE', 'GCP'}
        if target_provider and target_provider not in valid_providers:
            self.stderr.write(self.style.ERROR(
                f"Invalid provider '{target_provider}'. Choose from AWS, Azure, GCP."
            ))
            return

        active_providers = [target_provider] if target_provider else ['AWS', 'AZURE', 'GCP']

        self.stdout.write(self.style.NOTICE(
            f"=== CloudWise Pricing Refresh: {', '.join(active_providers)} in '{region}' ==="
        ))

        cutoff = dj_timezone.now() - timedelta(hours=max_age_hours)
        stats = {'refreshed': 0, 'skipped': 0, 'errors': 0}

        for tier in REPRESENTATIVE_SPEC_TIERS:
            tier_name = tier['tier']
            vcpu = tier['vcpu']
            ram_gb = tier['ram_gb']
            storage_gb = tier['storage_gb']

            self.stdout.write(f"\nProcessing {tier_name} ({vcpu} vCPU / {ram_gb} GB RAM):")

            # 1. AWS
            if 'AWS' in active_providers:
                aws_instance = tier['aws_instance']
                self._process_provider(
                    provider='AWS',
                    instance_type=aws_instance,
                    region=region,
                    fetch_func=lambda: get_aws_price_snapshot(
                        instance_type=aws_instance,
                        region=region,
                        vcpu=vcpu,
                        ram_gb=ram_gb,
                        storage_gb=storage_gb,
                        fallback_on_error=True,
                    ),
                    cutoff=cutoff,
                    force=force,
                    stats=stats,
                )

            # 2. Azure
            if 'AZURE' in active_providers:
                azure_sku = tier['azure_sku']
                self._process_provider(
                    provider='Azure',
                    instance_type=azure_sku,
                    region=region,
                    fetch_func=lambda: get_azure_price_snapshot(
                        vcpu=vcpu,
                        ram_gb=ram_gb,
                        storage_gb=storage_gb,
                        region=region,
                        sku=azure_sku,
                    ),
                    cutoff=cutoff,
                    force=force,
                    stats=stats,
                )

            # 3. GCP
            if 'GCP' in active_providers:
                gcp_type = tier['gcp_type']
                self._process_provider(
                    provider='GCP',
                    instance_type=gcp_type,
                    region=region,
                    fetch_func=lambda: get_gcp_price_snapshot(
                        vcpu=vcpu,
                        ram_gb=ram_gb,
                        storage_gb=storage_gb,
                        region=region,
                    ),
                    cutoff=cutoff,
                    force=force,
                    stats=stats,
                )

        self.stdout.write(self.style.SUCCESS(
            f"\nRefresh Complete! Refreshed: {stats['refreshed']}, Skipped (recent): {stats['skipped']}, Errors: {stats['errors']}"
        ))

    def _process_provider(self, provider, instance_type, region, fetch_func, cutoff, force, stats):
        existing = CloudPricingCache.objects.filter(
            provider=provider,
            instance_type=instance_type,
            region=region,
        ).first()

        if existing and not force and existing.last_updated >= cutoff:
            self.stdout.write(f"  [{provider}] {instance_type} - Skipped (refreshed {existing.last_updated.strftime('%Y-%m-%d %H:%M')})")
            stats['skipped'] += 1
            return

        try:
            snapshot = fetch_func()
            monthly_inr = Decimal(str(snapshot.get('monthlyInr', 0)))
            hourly_usd = Decimal(str(snapshot.get('hourlyUsd', 0.0)))
            source = snapshot.get('source', 'API')
            specs = snapshot.get('specs', {})

            cache_entry, created = CloudPricingCache.objects.update_or_create(
                provider=provider,
                instance_type=instance_type,
                region=region,
                defaults={
                    'price_per_month': monthly_inr,
                    'hourly_usd': hourly_usd,
                    'specs': specs,
                    'source': source,
                    'estimated': bool(snapshot.get('estimated', False)),
                },
            )
            action = 'Created' if created else 'Updated'
            self.stdout.write(self.style.SUCCESS(
                f"  [{provider}] {instance_type} - {action}: INR {monthly_inr}/mo ({source})"
            ))
            stats['refreshed'] += 1
        except Exception as exc:
            self.stderr.write(self.style.ERROR(
                f"  [{provider}] {instance_type} - Error: {exc}"
            ))
            stats['errors'] += 1
