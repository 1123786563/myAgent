from decimal import Decimal, ROUND_HALF_UP

def to_decimal(val):
    if val is None:
        return Decimal('0.00')
    try:
        if isinstance(val, (int, float, str)):
            return Decimal(str(val)).quantize(Decimal('0.00'), rounding=ROUND_HALF_UP)
        return Decimal(val).quantize(Decimal('0.00'), rounding=ROUND_HALF_UP)
    except Exception:
        return Decimal('0.00')
