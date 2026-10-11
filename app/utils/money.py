"""Marketplace currency and customer-facing formatting; stored amounts are USD."""
from decimal import Decimal

CURRENCY_CODE = "USD"


def format_money(amount):
    return f"${Decimal(str(amount)):.2f}"
