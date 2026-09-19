"""`trade` 命令组：工作类型（工种）与单价管理。

改单价的影响必须可见
--------------------
合计是**按当前单价实时重算**的（见 bill_recompute 模块说明），不是存死在账单里。
所以改价会立刻改变已有账单的金额——这是 GUI 的既有语义，CLI 必须保持一致，
否则同一份数据用 GUI 看和用 CLI 看会得出不同结果。

因此 trade.update 会返回影响范围（affected_bills / total_before / total_after），
让调用方看得见后果，而不是静默改钱。
"""

from __future__ import annotations

import argparse

from ...bill_recompute import summarize_bill_calculations
from ...billing import Billing
from ...money import validate_price
from ...project_service import require_editable, save_trade, update_trade_fields
from ...trade_item import TradeItem
from ...trade_item_id import generate_trade_item_id
from .. import common
from ..common import op_map, require_project
from ..errors import InvalidArgument, ProjectNotFound
from ..registry import ArgSpec, CommandSpec, register


def _trade_view(item: TradeItem, project=None) -> dict:
    billing = Billing.from_dict(item.to_dict())
    category = item.category
    if not category and project is not None and item.category_id:
        category = next(
            (c.name for c in project.category_order if c.id == item.category_id),
            "",
        )
    return {
        "id": item.id,
        "name": item.name,
        "category": category,
        "category_id": item.category_id,
        "has_unit": billing.has_unit,
        "unit_price": billing.unit_price,
        "unit": billing.unit,
        "price_display": billing.format_price(),
    }


def _find_trade(project, trade_id: str) -> TradeItem:
    for item in project.trade_items:
        if getattr(item, "id", "") == trade_id:
            return item
    raise ProjectNotFound(
        f"工作类型不存在: {trade_id}",
        details={
            "uuid": project.project_uuid,
            "trade_id": trade_id,
            "available": [i.id for i in project.trade_items],
        },
    )


def _project_totals(project) -> float:
    """按当前单价重算项目合计（用于对比改价前后）。"""
    bills = [b.to_dict() if hasattr(b, "to_dict") else dict(b) for b in project.bills]
    items = [
        i.to_dict() if hasattr(i, "to_dict") else dict(i) for i in project.trade_items
    ]
    _calcs, total, _errors = summarize_bill_calculations(bills, items, op_map())
    return total


def _affected_bill_count(project, trade_id: str) -> int:
    return sum(1 for b in project.bills if getattr(b, "trade_item_id", "") == trade_id)


def _parse_price(value) -> float:
    try:
        return validate_price(value)
    except ValueError as exc:
        raise InvalidArgument(str(exc)) from exc


def _ensure_editable(project) -> None:
    require_editable(project)


def _trade_list(args: argparse.Namespace) -> dict:
    project = require_project(args.uuid)
    items = [_trade_view(i, project) for i in project.trade_items]
    if args.name_contains:
        items = [i for i in items if args.name_contains in i["name"]]
    return {
        "uuid": project.project_uuid,
        "name": project.name,
        "count": len(items),
        "categories": [c.name for c in project.category_order],
        "trade_items": items,
    }


def _trade_add(args: argparse.Namespace) -> dict:
    project = require_project(args.uuid)
    _ensure_editable(project)

    name = (args.name or "").strip()
    if not name:
        raise InvalidArgument("工作类型名称不能为空")
    if any(i.name == name for i in project.trade_items):
        raise InvalidArgument(f"工作类型已存在: {name}", details={"name": name})

    has_unit = not args.no_unit
    if has_unit:
        if args.unit_price is None:
            raise InvalidArgument("按单价计费时必须提供 --unit-price")
        unit_price = _parse_price(args.unit_price)
    else:
        if args.unit_price is not None:
            raise InvalidArgument("--no-unit 与 --unit-price 不能同时使用")
        unit_price = 0.0

    category_name = (args.category or "").strip()
    category_id = project.ensure_category(category_name)

    item = TradeItem(
        id=generate_trade_item_id(),
        category_id=category_id,
        name=name,
        has_unit=has_unit,
        unit_price=unit_price,
        unit=(args.unit or "") if has_unit else "",
        category=category_name,
    )
    item = save_trade(project, item)
    common.project_manager.update_project(args.uuid, project)

    refreshed = require_project(args.uuid)
    return _trade_view(_find_trade(refreshed, item.id), refreshed)


def _trade_update(args: argparse.Namespace) -> dict:
    project = require_project(args.uuid)
    _ensure_editable(project)
    item = _find_trade(project, args.trade_id)

    # 注意：no_unit 是 store_true 旗标，默认值是 False 而非 None，
    # 因此不能用 `is not None` 判断——否则"什么都没传"也会被当成有改动。
    touched = bool(args.no_unit) or any(
        v is not None for v in (args.name, args.unit_price, args.unit, args.category)
    )
    if not touched:
        raise InvalidArgument("未指定任何要修改的字段")

    before_total = _project_totals(project)
    affected = _affected_bill_count(project, item.id)
    before = _trade_view(item, project)

    update_trade_fields(
        item,
        name=args.name if args.name is not None else item.name,
        category=args.category if args.category is not None else item.category,
        has_unit=False
        if args.no_unit
        else (True if args.unit_price is not None else item.has_unit),
        unit_price=args.unit_price if args.unit_price is not None else item.unit_price,
        unit=args.unit if args.unit is not None else item.unit,
    )
    item = save_trade(project, item)

    common.project_manager.update_project(args.uuid, project)
    refreshed = require_project(args.uuid)
    after_total = _project_totals(refreshed)

    return {
        "before": before,
        "after": _trade_view(_find_trade(refreshed, args.trade_id), refreshed),
        # 改价会立刻改变已有账单金额（合计实时重算），故显式回报影响
        "affected_bills": affected,
        "total_before": before_total,
        "total_after": after_total,
        "total_delta": round(after_total - before_total, 2),
    }


register(
    CommandSpec(
        name="trade.list",
        help="列出工作类型（工种）与单价",
        handler=_trade_list,
        read_only=True,
        args=(
            ArgSpec(name="uuid", help="项目 UUID", kind="positional"),
            ArgSpec(name="name_contains", help="按名称包含子串筛选"),
        ),
        examples=("cpa trade.list <uuid> --json",),
    )
)

register(
    CommandSpec(
        name="trade.add",
        help="新增工作类型（含单价）",
        handler=_trade_add,
        read_only=False,
        args=(
            ArgSpec(name="uuid", help="项目 UUID", kind="positional"),
            ArgSpec(name="name", help="工种名称，如 找平"),
            ArgSpec(name="unit_price", help="单价（支持小数，如 12.5）"),
            ArgSpec(name="unit", help="单位，如 m2 / m3"),
            ArgSpec(name="category", help="所属分类（不存在则自动创建）"),
            ArgSpec(
                name="no_unit", help="无单价计费（与 --unit-price 互斥）", type="flag"
            ),
        ),
        examples=(
            "cpa trade.add <uuid> --name 找平 --unit-price 25 --unit m2 --json",
            "cpa trade.add <uuid> --name 杂项 --no-unit --json",
        ),
    )
)

register(
    CommandSpec(
        name="trade.update",
        help="修改工作类型（单价/名称/单位/分类）；返回对已有账单的影响",
        handler=_trade_update,
        read_only=False,
        args=(
            ArgSpec(name="uuid", help="项目 UUID", kind="positional"),
            ArgSpec(name="trade_id", help="工作类型 ID", kind="positional"),
            ArgSpec(name="name", help="新名称"),
            ArgSpec(name="unit_price", help="新单价"),
            ArgSpec(name="unit", help="新单位"),
            ArgSpec(name="category", help="新分类"),
            ArgSpec(name="no_unit", help="改为无单价计费", type="flag"),
        ),
        examples=("cpa trade.update <uuid> ti_wall --unit-price 50 --json",),
    )
)
