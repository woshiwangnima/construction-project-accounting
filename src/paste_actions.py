"""复制粘贴的纯函数层：把剪贴板 payload 转换为可直接 append 到项目的对象。

函数
----
- `paste_bill(payload, target_trade_items, now)` -> 新账单 dict
- `paste_trade_item(payload, target_trade_items, target_category_order, now)` -> 新 TradeItem

设计原则
--------
- 纯函数：不碰 Tkinter / messagebox / 磁盘
- 不变性：不修改 payload / target_trade_items
- 跨项目孤儿：trade_item_id 在目标项目找不到 → 直接产孤儿账单（带 frozen_snapshot）
- trade item id 重算：创建时生成新的 ti_ UUID，避免重名影响引用
- 名称去重：「X」→「X 副本」→「X 副本 2」…
"""
from __future__ import annotations

from datetime import datetime
from typing import Iterable

from .billing import Billing, write_billing
from .bill_recompute import recompute_bill_total  # noqa: F401  (re-exported for tests)
from .trade_item import TradeItem
from .trade_item_id import generate_trade_item_id, compute_bill_id


# ──────────────────────────────────────────────────────────────────────
# 工具
# ──────────────────────────────────────────────────────────────────────

def _now_str() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _unique_name(base: str, existing_names: Iterable[str]) -> str:
    """返回不与 existing_names 冲突的名字。

    序列：X → X 副本 → X 副本 2 → X 副本 3
    """
    existing = set(existing_names)
    if base not in existing:
        return base
    candidate = f"{base} 副本"
    if candidate not in existing:
        return candidate
    n = 2
    while True:
        candidate = f"{base} 副本 {n}"
        if candidate not in existing:
            return candidate
        n += 1


def _deepcopy_safe(obj):
    """JSON 兼容结构深克隆。"""
    if isinstance(obj, dict):
        return {k: _deepcopy_safe(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_deepcopy_safe(v) for v in obj]
    return obj


# ──────────────────────────────────────────────────────────────────────
# 账单粘贴
# ──────────────────────────────────────────────────────────────────────

def paste_bill(
    payload: dict,
    target_trade_items: list[dict],
    *,
    now: str | None = None,
) -> dict:
    """把剪贴板里的账单 payload 转换为可直接 append 到目标项目的新账单。

    参数
    ----
    payload : 剪贴板存的账单 payload
        必含字段：content / trade_item_id / trade_item_name_fallback
        可选字段：note / work_date_type / work_date_start / work_date_end
                  / frozen_snapshot / frozen_total / _needs_attention
    target_trade_items : 目标项目当前所有 trade items
        用于按 trade_item_id 解析（找不到 → 产孤儿）
    now : 落盘的 record_time（测试用）

    返回
    ----
    新账单 dict。可直接 `project["bills"].append(result)`。
    永远生成新 id（compute_bill_id 派生），不与源重复。
    """
    now = now or _now_str()
    new_bill: dict = {
        "content": payload["content"],
        "trade_item_id": "",  # 先占位，下文按解析结果覆盖
        "work_date_type": payload.get("work_date_type", "无时间"),
        "work_date_start": payload.get("work_date_start", "") or payload.get("work_date", ""),
        "work_date_end": payload.get("work_date_end", ""),
        "record_time": now,
    }
    if payload.get("note"):
        new_bill["note"] = payload["note"]

    # ── 解析 trade_item_id ──
    source_tid = payload.get("trade_item_id", "")
    match = next(
        (ti for ti in target_trade_items if ti.get("id") == source_tid),
        None,
    )
    if match is not None:
        new_bill["trade_item_id"] = source_tid
    else:
        # 找不到 trade item：粘贴为孤儿
        new_bill["trade_item_id"] = ""
        if payload.get("frozen_snapshot"):
            new_bill["frozen_snapshot"] = _deepcopy_safe(payload["frozen_snapshot"])
        if payload.get("frozen_total") is not None:
            new_bill["frozen_total"] = payload["frozen_total"]
        new_bill["_needs_attention"] = True

    new_bill["id"] = compute_bill_id(
        new_bill["trade_item_id"],
        new_bill["content"],
        new_bill["record_time"],
    )
    return new_bill


# ──────────────────────────────────────────────────────────────────────
# 工作类型粘贴
# ──────────────────────────────────────────────────────────────────────

def paste_trade_item(
    payload: dict,
    target_trade_items: list[dict],
    target_category_order: list[str] | None = None,
) -> dict:
    """把剪贴板里的 trade item payload 转换为可直接 append 到目标项目的新 trade item。

    返回
    ----
    新 trade item dict。可直接 `project["trade_items"].append(result)`。

    注意
    ----
    - id 永远重算（不与源 / 目标撞车）
    - 名称自动去重：「X」→「X 副本」→…
    - category_order 不在此函数里改，由调用方（ContentArea）追加新分类
    """
    cat = payload["category"]
    base_name = payload["name"]
    new_name = _unique_name(base_name, (ti.get("name", "") for ti in target_trade_items))
    billing = Billing(
        has_unit=payload["has_unit"],
        unit_price=payload["unit_price"],
        unit=payload["unit"],
    )
    category_id = ""
    for c in target_category_order or []:
        if getattr(c, "name", c) == cat:
            category_id = getattr(c, "id", "")
            break
    new_ti = TradeItem(
        id=generate_trade_item_id(),
        category_id=category_id,
        category=cat,
        name=new_name,
        has_unit=billing.has_unit,
        unit_price=billing.unit_price,
        unit=billing.unit,
    )
    return new_ti


def unique_category_after_paste(
    cat: str,
    target_category_order: list[str],
) -> bool:
    """判断粘贴时是否要把 cat 追加到 target_category_order 末尾。"""
    return cat not in [getattr(c, "name", c) for c in target_category_order]
