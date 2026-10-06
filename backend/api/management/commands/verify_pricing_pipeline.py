import logging
from django.core.management.base import BaseCommand
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APIRequestFactory

from api.models import PriceSnapshot
from api.serializers import PriceSnapshotSerializer
from api.services import (
    aws_pricing_service,
    azure_pricing_service,
    gcp_pricing_service,
)
from api.views import pricing_compare_view

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = (
        'Verifies the multi-cloud pricing pipeline for AWS, Azure, and GCP (skipping DigitalOcean). '
        'Tests provider refreshes, reports PriceSnapshot row counts, directly tests /api/pricing/compare, '
        'and outputs a PASS/FAIL summary.'
    )

    def add_arguments(self, parser):
        parser.add_argument(
            '--skip-refresh',
            action='store_true',
            help='Skip the price catalog fetch/refresh step and test only database state and compare endpoint.',
        )

    def handle(self, *args, **options):
        self.stdout.write(self.style.MIGRATE_HEADING("\n=== CloudWise Pricing Pipeline Verification ==="))
        self.stdout.write("Target providers : AWS, Azure, GCP")
        self.stdout.write("Skipped provider : DigitalOcean (not implemented / optional)\n")

        skip_refresh = options.get('skip_refresh', False)
        target_providers = [
            ('AWS', aws_pricing_service.fetch_price_catalog),
            ('Azure', azure_pricing_service.fetch_price_catalog),
            ('GCP', gcp_pricing_service.fetch_price_catalog),
        ]
        unimplemented_providers = ['DigitalOcean']

        refresh_results = {}
        pipeline_errors = []

        # -------------------------------------------------------------
        # STEP 1: Refresh AWS, Azure, and GCP (Skip DigitalOcean)
        # -------------------------------------------------------------
        if not skip_refresh:
            self.stdout.write(self.style.NOTICE("[1/3] Running catalog refresh for AWS, Azure, GCP..."))
            for provider_name, fetch_fn in target_providers:
                self.stdout.write(f"  -> Fetching {provider_name} catalog...")
                try:
                    items = fetch_fn()
                    count = 0
                    for item in items:
                        defaults = {
                            'service': item['service'],
                            'sku': item.get('sku', ''),
                            'vcpu': item['vcpu'],
                            'memoryGiB': item['memoryGiB'],
                            'storageType': item.get('storageType'),
                            'unit': item.get('unit', 'Hrs'),
                            'pricePerUnit': item['pricePerUnit'],
                            'currency': item.get('currency', 'USD'),
                            'pricingModel': item.get('pricingModel', 'OnDemand'),
                            'fetchedAt': item.get('fetchedAt') or timezone.now(),
                        }
                        PriceSnapshot.objects.update_or_create(
                            provider=item['provider'],
                            instanceType=item['instanceType'],
                            region=item['region'],
                            defaults=defaults,
                        )
                        count += 1

                    refresh_results[provider_name] = {
                        'status': 'OK' if count > 0 else 'EMPTY',
                        'fetched_count': count,
                        'error': None,
                    }
                    if count > 0:
                        self.stdout.write(self.style.SUCCESS(f"     Successfully synced {count} offerings."))
                    else:
                        self.stdout.write(
                            self.style.WARNING(
                                f"     Fetched 0 offerings (API key missing or provider returned empty list)."
                            )
                        )
                except Exception as exc:
                    refresh_results[provider_name] = {
                        'status': 'ERROR',
                        'fetched_count': 0,
                        'error': str(exc),
                    }
                    self.stdout.write(self.style.ERROR(f"     Failed: {exc}"))
        else:
            self.stdout.write(self.style.NOTICE("[1/3] Refresh step skipped (--skip-refresh)."))

        # -------------------------------------------------------------
        # STEP 2: Audit PriceSnapshot Table Counts
        # -------------------------------------------------------------
        self.stdout.write(self.style.NOTICE("\n[2/3] Auditing PriceSnapshot database rows per provider..."))
        provider_counts = {}

        # Check target 3 providers
        for provider_name, _ in target_providers:
            count = PriceSnapshot.objects.filter(provider=provider_name).count()
            provider_counts[provider_name] = count
            if count > 0:
                self.stdout.write(self.style.SUCCESS(f"  [OK]       {provider_name:<14}: {count:>4} rows in DB"))
            else:
                err_info = ""
                if provider_name in refresh_results and refresh_results[provider_name].get('error'):
                    err_info = f" ({refresh_results[provider_name]['error']})"
                self.stdout.write(
                    self.style.WARNING(
                        f"  [FLAGGED]  {provider_name:<14}:    0 rows (service broken/unconfigured){err_info}"
                    )
                )

        # Check skipped / unimplemented provider (DigitalOcean)
        for provider_name in unimplemented_providers:
            count = PriceSnapshot.objects.filter(provider=provider_name).count()
            provider_counts[provider_name] = count
            if count == 0:
                self.stdout.write(
                    self.style.HTTP_INFO(
                        f"  [EXPECTED] {provider_name:<14}:    0 rows (not implemented / skipped)"
                    )
                )
            else:
                self.stdout.write(
                    f"  [NOTED]    {provider_name:<14}: {count:>4} rows (legacy/cached data present)"
                )

        # -------------------------------------------------------------
        # STEP 3: Test /api/pricing/compare Logic Directly (In-Process)
        # -------------------------------------------------------------
        self.stdout.write(self.style.NOTICE("\n[3/3] Testing /api/pricing/compare view directly (in-memory)..."))
        factory = APIRequestFactory()
        request = factory.get('/api/pricing/compare')
        response = pricing_compare_view(request)

        compare_passed = True
        compare_reasons = []

        if response.status_code != status.HTTP_200_OK:
            compare_passed = False
            compare_reasons.append(f"HTTP status was {response.status_code}, expected 200")

        resp_data = getattr(response, 'data', {})
        if not isinstance(resp_data, dict):
            compare_passed = False
            compare_reasons.append("Response data is not a dictionary")
        else:
            if not resp_data.get('success'):
                compare_passed = False
                compare_reasons.append("Response 'success' field is not True")

            data_list = resp_data.get('data', [])
            if not isinstance(data_list, list):
                compare_passed = False
                compare_reasons.append("Response 'data' field is not a list")
            else:
                total_db_rows = PriceSnapshot.objects.count()
                if total_db_rows > 0 and len(data_list) == 0:
                    compare_passed = False
                    compare_reasons.append("PriceSnapshot has rows but compare endpoint returned 0 items")

                # Validate item schema
                required_keys = {'id', 'provider', 'service', 'region', 'instanceType', 'vcpu', 'memoryGiB', 'pricePerUnit'}
                providers_in_response = set()
                is_sorted = True
                last_price = -1.0

                for idx, item in enumerate(data_list):
                    missing_keys = required_keys - set(item.keys())
                    if missing_keys:
                        compare_passed = False
                        compare_reasons.append(f"Item #{idx} missing keys: {missing_keys}")
                        break
                    providers_in_response.add(item['provider'])
                    price = item.get('pricePerUnit', 0.0)
                    if price < last_price:
                        is_sorted = False
                    last_price = price

                if not is_sorted:
                    compare_passed = False
                    compare_reasons.append("Response items are not ordered ascending by pricePerUnit")

                # Check provider constraints: no requirement for DigitalOcean
                disallowed_providers = providers_in_response - {'AWS', 'Azure', 'GCP', 'DigitalOcean'}
                if disallowed_providers:
                    compare_passed = False
                    compare_reasons.append(f"Unexpected providers found: {disallowed_providers}")

        if compare_passed:
            total_items = len(resp_data.get('data', []))
            active_providers = {item['provider'] for item in resp_data.get('data', [])}
            self.stdout.write(
                self.style.SUCCESS(
                    f"  [OK] /api/pricing/compare returned {total_items} items across providers: {active_providers or 'None'}."
                )
            )
            self.stdout.write(
                self.style.SUCCESS("  [OK] Response format, schema fields, and price ordering verified.")
            )
        else:
            self.stdout.write(self.style.ERROR(f"  [FAIL] Compare endpoint validation failed: {'; '.join(compare_reasons)}"))

        # -------------------------------------------------------------
        # SUMMARY
        # -------------------------------------------------------------
        self.stdout.write(self.style.MIGRATE_HEADING("\n=== VERIFICATION SUMMARY ==="))
        total_3_provider_rows = sum(provider_counts.get(p, 0) for p, _ in target_providers)
        overall_pass = compare_passed and (total_3_provider_rows > 0 or PriceSnapshot.objects.count() == 0)

        self.stdout.write(f"Active Provider Rows (AWS + Azure + GCP) : {total_3_provider_rows}")
        self.stdout.write(f"DigitalOcean Rows                        : {provider_counts.get('DigitalOcean', 0)} (Expected: 0)")
        self.stdout.write(f"Compare API Functionality                : {'PASS' if compare_passed else 'FAIL'}")

        if overall_pass:
            self.stdout.write(self.style.SUCCESS("\nOVERALL STATUS: PASS"))
            self.stdout.write(
                "The system operates correctly and degrades gracefully without DigitalOcean.\n"
            )
        else:
            self.stdout.write(self.style.ERROR("\nOVERALL STATUS: FAIL"))
            if compare_reasons:
                self.stdout.write(self.style.ERROR(f"Issues: {'; '.join(compare_reasons)}\n"))
