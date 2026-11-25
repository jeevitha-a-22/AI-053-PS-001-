"""
Currency and decimal utility helpers.
Ensures high precision financial calculations using Decimal.
"""
from decimal import Decimal, ROUND_HALF_UP, InvalidOperation
from typing import Union


def to_decimal(val: Union[Decimal, int, float, str, None], default: Decimal = Decimal('0')) -> Decimal:
    """Safely convert any numeric or string representation to Decimal."""
    if val is None:
        return default
    if isinstance(val, Decimal):
        return val
    try:
        # String conversion of float avoids binary floating point representation issues
        val_str = str(val).strip()
        if not val_str:
            return default
        return Decimal(val_str)
    except (InvalidOperation, ValueError):
        return default


def round_currency(amount: Union[Decimal, int, float, str, None]) -> Decimal:
    """Round monetary amount to 2 decimal places (paise) using ROUND_HALF_UP."""
    dec_amount = to_decimal(amount)
    return dec_amount.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)


def round_rupee(amount: Union[Decimal, int, float, str, None]) -> Decimal:
    """Round monetary amount to the nearest whole rupee using ROUND_HALF_UP (BR-07)."""
    dec_amount = to_decimal(amount)
    return dec_amount.quantize(Decimal('1'), rounding=ROUND_HALF_UP)
