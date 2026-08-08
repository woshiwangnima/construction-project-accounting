"""账单合计实时重算。

设计目的
--------
- 旧实现把 total 写死在 bill 字典里——trade item 改价后必须手动同步。
- 新实现：每次显示都从公式 + 当前 trade item 单价重算，保证实时一致。
- 孤儿账单没有可重算的来源，回退到 frozen_total（软删除时定格的合计）。

错误处理
--------
- 公式解析失败：返回 0.0，记日志，不抛异常。
- 缺 content 字段：返回 0.0。
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from typing import Optional

from .billing import Billing, read_billing
from .billing_resolver import build_trade_item_index
from .logger import logger


_CENT = Decimal("0.01")


def _as_decimal(value) -> Decimal:
    if value is None or value == "":
        return Decimal("0")
    try:
        return Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return Decimal("0")


def _money(value: Decimal) -> Decimal:
    return value.quantize(_CENT, rounding=ROUND_HALF_UP)


def _frozen_total(bill: dict) -> float:
    return float(_money(_as_decimal(bill.get("frozen_total", 0))))


@dataclass(frozen=True)
class BillCalculation:
    """One-pass bill calculation data used by list and summary rendering."""

    total: float
    canonical: str | None
    formula_value: Decimal | None
    formula_error: bool
    trade_item: dict | None
    billing: Billing
    category: str
    name: str
    orphan: bool


def _parse_content(content: str, op_map: dict) -> tuple[str | None, Optional[Decimal], bool]:
    """Normalize and evaluate a formula once.

    Returns ``(canonical, value, error)``. Empty input is not an error.
    """
    if not content:
        return None, None, False
    try:
        from .calculator import evaluate_decimal, to_canonical
        canonical = to_canonical(content, op_map or {})
        return canonical, evaluate_decimal(canonical), False
    except Exception as exc:
        logger.debug("公式求值失败: content=%r err=%s", content, exc)
        return None, None, True


def _eval_content(content: str, op_map: dict) -> Optional[Decimal]:
    """用计算器求值；失败返回 None。保留给旧调用方使用。"""
    _canonical, value, _error = _parse_content(content, op_map)
    return value


def calculate_bill(
    bill: dict,
    trade_items: list[dict],
    op_map: dict,
    trade_item_index: dict[str, dict] | None = None,
    parse_formula: bool = True,
) -> BillCalculation:
    """Calculate all display-relevant values for one bill in one pass."""
    if not bill:
        return BillCalculation(
            total=0.0,
            canonical=None,
            formula_value=None,
            formula_error=False,
            trade_item=None,
            billing=Billing(),
            category="",
            name="",
            orphan=True,
        )

    index = trade_item_index if trade_item_index is not None else build_trade_item_index(trade_items)
    tid = bill.get("trade_item_id", "")
    trade_item = index.get(str(tid)) if tid else None
    orphan = trade_item is None

    snapshot = bill.get("frozen_snapshot") or {}
    label_source = trade_item or (snapshot if isinstance(snapshot, dict) else {})
    billing = read_billing(label_source) if label_source else Billing()
    category = label_source.get("category", "") if isinstance(label_source, dict) else ""
    name = label_source.get("name", "") if isinstance(label_source, dict) else ""

    canonical = None
    formula_value = None
    formula_error = False
    if parse_formula:
        canonical, formula_value, formula_error = _parse_content(
            bill.get("content", ""), op_map
        )

    if orphan:
        total = _frozen_total(bill)
    elif formula_value is None:
        total = 0.0
    elif billing.is_per_unit:
        total = float(_money(formula_value * _as_decimal(billing.unit_price)))
    else:
        total = float(_money(formula_value))

    return BillCalculation(
        total=total,
        canonical=canonical,
        formula_value=formula_value,
        formula_error=formula_error,
        trade_item=trade_item,
        billing=billing,
        category=category,
        name=name,
        orphan=orphan,
    )


def prepare_bill_calculations(
    bills: list[dict] | None,
    trade_items: list[dict] | None,
    op_map: dict | None,
) -> list[BillCalculation]:
    """Prepare all bill values with one trade-item index per render pass."""
    items = trade_items or []
    index = build_trade_item_index(items)
    return [
        calculate_bill(bill, items, op_map or {}, index, parse_formula=True)
        for bill in (bills or [])
    ]


def summarize_bill_calculations(
    bills: list[dict] | None,
    trade_items: list[dict] | None,
    op_map: dict | None,
) -> tuple[list[BillCalculation], float, int]:
    """Return per-row calculations, total amount and formula error count."""
    calculations = prepare_bill_calculations(bills, trade_items, op_map)
    total = sum(item.total for item in calculations)
    error_count = sum(
        1
        for bill, item in zip(bills or [], calculations)
        # Keep the existing UI contract: zero total + non-empty formula is
        # shown as a calculation warning, including legacy/orphan records.
        if bill.get("content", "") and item.total == 0
    )
    return calculations, total, error_count


def recompute_bill_total(
    bill: dict,
    trade_items: list[dict],
    op_map: dict,
    trade_item_index: dict[str, dict] | None = None,
) -> float:
    """重算账单合计。

    - 命中：result * unit_price（无单价时直接 result）。
    - 孤儿：用 bill.frozen_total（软删除时定格值），无则 0。
    - 公式错：0。
    """
    return calculate_bill(
        bill,
        trade_items or [],
        op_map or {},
        trade_item_index=trade_item_index,
        parse_formula=True,
    ).total
