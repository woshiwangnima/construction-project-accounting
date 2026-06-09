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

from typing import Callable, Optional

from .logger import logger


def _eval_content(content: str, op_map: dict) -> Optional[float]:
    """用计算器求值；失败返回 None。"""
    if not content:
        return None
    try:
        from .calculator import to_canonical, evaluate_canonical, MathParseError
        canonical = to_canonical(content, op_map or {})
        return evaluate_canonical(canonical)
    except Exception as exc:
        logger.debug("公式求值失败: content=%r err=%s", content, exc)
        return None


def recompute_bill_total(
    bill: dict,
    trade_items: list[dict],
    op_map: dict,
) -> float:
    """重算账单合计。

    - 命中：result * unit_price（无单价时直接 result）。
    - 孤儿：用 bill.frozen_total（软删除时定格值），无则 0。
    - 公式错：0。
    """
    if not bill:
        return 0.0
    tid = bill.get("trade_item_id", "")
    if not tid:
        # 孤儿：用冻结合计
        return float(bill.get("frozen_total", 0) or 0)

    ti = None
    for it in trade_items or []:
        if it.get("id") == tid:
            ti = it
            break
    if ti is None:
        return float(bill.get("frozen_total", 0) or 0)

    result = _eval_content(bill.get("content", ""), op_map)
    if result is None:
        return 0.0

    from .billing import read_billing
    billing = read_billing(ti)
    if billing.is_per_unit:
        return round(result * billing.unit_price, 2)
    return round(result, 2)
