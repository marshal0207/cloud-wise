from decimal import Decimal
import os

DEFAULT_USD_TO_INR_RATE = Decimal('83.0')


def get_usd_to_inr_rate() -> Decimal:
    """
    Return the shared USD -> INR exchange rate across all cloud providers.
    Ensures AWS, Azure, and GCP comparisons use the exact same rate.
    """
    raw_rate = os.getenv('USD_TO_INR_RATE', '').strip()
    if not raw_rate:
        return DEFAULT_USD_TO_INR_RATE
    try:
        return Decimal(raw_rate)
    except Exception:
        return DEFAULT_USD_TO_INR_RATE
