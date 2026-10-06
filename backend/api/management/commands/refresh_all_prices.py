import logging
from django.core.management.base import BaseCommand
from django.utils import timezone
from api.models import PriceSnapshot
from api.services import (
    aws_pricing_service,
    azure_pricing_service,
    gcp_pricing_service,
)

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = 'Fetches normalized pricing from AWS, Azure, and GCP and upserts into PriceSnapshot.'

    def handle(self, *args, **options):
        providers = [
            ('AWS', aws_pricing_service.fetch_price_catalog),
            ('Azure', azure_pricing_service.fetch_price_catalog),
            ('GCP', gcp_pricing_service.fetch_price_catalog),
        ]

        total_upserted = 0
        total_failed_providers = 0

        self.stdout.write(self.style.NOTICE("Starting multi-cloud pricing refresh..."))

        for provider_name, fetch_fn in providers:
            self.stdout.write(f"Fetching pricing for {provider_name}...")
            try:
                items = fetch_fn()
                provider_count = 0
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
                    snapshot, created = PriceSnapshot.objects.update_or_create(
                        provider=item['provider'],
                        instanceType=item['instanceType'],
                        region=item['region'],
                        defaults=defaults,
                    )
                    provider_count += 1

                total_upserted += provider_count
                self.stdout.write(
                    self.style.SUCCESS(f"Successfully processed {provider_count} offerings for {provider_name}.")
                )

            except Exception as exc:
                total_failed_providers += 1
                error_msg = f"Failed to refresh prices for provider {provider_name}: {exc}"
                logger.error(error_msg, exc_info=True)
                self.stderr.write(self.style.ERROR(error_msg))
                # Continue with the next provider — never let one provider's failure block the others
                continue

        self.stdout.write(
            self.style.SUCCESS(
                f"Completed refresh. Total snapshots upserted: {total_upserted}. "
                f"Failed providers: {total_failed_providers}."
            )
        )
