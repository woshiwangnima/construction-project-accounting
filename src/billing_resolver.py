"""账单 ↔ trade item 解析器。

设计目的
--------
- 统一所有"根据账单取 trade item"的入口。
- 找不到（孤儿）时回退到 `frozen_snapshot`。
- 渲染层（列表、合计、导出）只调一次本模块，不再各自处理缺失场景。

约定
----
- Bill 必含 `trade_item_id`（普通账单）或 `""`（孤儿）+ 可选 `frozen_snapshot`。
- Trade item 必含 `id` 字段（见 `src/trade_item_id.py`）。
- 找不到时返回 `None`（resolver）或 `Billing` from frozen_snapshot（resolve_billing）。
"""
from __future__ import annotations

from typing import Optional

from .billing import Billing, read_billing


def resolve_trade_item(
    bill: dict, trade_items: list[dict]
) -> Optional[dict]:
    """按 bill.trade_item_id 查找对应的 trade item。

    返回：
    - 命中：对应 trade item 字典
    - 未命中（包括 bill 缺 trade_item_id）：None
    """
    tid = (bill or {}).get("trade_item_id", "")
    if not tid:
        return None
    for ti in trade_items or []:
        if ti.get("id") == tid:
            return ti
    return None


def is_orphan(bill: dict, trade_items: Optional[list[dict]] = None) -> bool:
    """账单是否为孤儿。

    - 不传 trade_items：仅按 trade_item_id 是否为空判断（结构孤儿）。
    - 传 trade_items：trade_item_id 非空但解析不到也算孤儿。
    """
    bill = bill or {}
    tid = bill.get("trade_item_id", "")
    if not tid:
        return True
    if trade_items is None:
        return False
    return resolve_trade_item(bill, trade_items) is None


def resolve_billing(
    bill: dict, trade_items: list[dict]
) -> Billing:
    """解析账单的计费三件套。

    - 命中：直接读 trade item 的 Billing。
    - 孤儿：尝试从 bill.frozen_snapshot 还原 Billing。
    - 都没有：用 Billing() 兜底（has_unit=True, price=1, unit=""）。
    """
    ti = resolve_trade_item(bill, trade_items)
    if ti is not None:
        return read_billing(ti)
    snap = (bill or {}).get("frozen_snapshot") or {}
    if snap:
        return read_billing(snap)
    return Billing()


def resolve_label(
    bill: dict, trade_items: list[dict]
) -> tuple[str, str]:
    """解析账单的 (类别, 名称) 用于显示。

    - 命中：返回 trade item 的 (category, name)。
    - 孤儿 + frozen_snapshot：返回 (snap.category, snap.name)。
    - 否则：返回 ("", "")。
    """
    ti = resolve_trade_item(bill, trade_items)
    if ti is not None:
        return (ti.get("category", ""), ti.get("name", ""))
    snap = (bill or {}).get("frozen_snapshot") or {}
    if snap:
        return (snap.get("category", ""), snap.get("name", ""))
    return ("", "")


def orphan_bills(bills: list[dict], trade_items: list[dict]) -> list[dict]:
    """筛出所有孤儿账单（结构孤儿 + tid 解析不到的）。"""
    return [b for b in (bills or []) if is_orphan(b, trade_items)]
