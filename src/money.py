"""Decimal arithmetic shared by summaries, previews and exports."""
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from collections.abc import Iterable

CENT = Decimal("0.01")


def as_decimal(value) -> Decimal:
    try:
        result = Decimal(str(value))
        return result if result.is_finite() else Decimal("0")
    except (InvalidOperation, TypeError, ValueError):
        return Decimal("0")


def round_money(value: Decimal) -> Decimal:
    return value.quantize(CENT, rounding=ROUND_HALF_UP)


def sum_money(values: Iterable) -> float:
    return float(sum((as_decimal(value) for value in values), Decimal("0")))


def validate_price(value) -> float:
    """Reject invalid input at edit boundaries; legacy loading stays tolerant."""
    try:
        price = Decimal(str(value))
        result = float(price)
    except (InvalidOperation, TypeError, ValueError, OverflowError) as exc:
        raise ValueError("单价请输入有效数字") from exc
    import math
    if not price.is_finite() or not math.isfinite(result) or price < 0:
        raise ValueError("单价必须是有限的非负数")
    return result
