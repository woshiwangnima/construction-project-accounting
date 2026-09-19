"""`bill` 命令组：账单列表与合计汇总。

合计一律走 `bill_recompute.summarize_bill_calculations`，它已覆盖
单价乘法、孤儿账单回退 frozen_total、每行 ROUND_HALF_UP 等口径；
自行求和会与 GUI 显示不一致。
"""

from __future__ import annotations

import argparse
from decimal import Decimal
from ...money import as_decimal

from ...bill_recompute import summarize_bill_calculations
from ..common import op_map, require_project
from ..errors import InvalidArgument
from ..registry import ArgSpec, CommandSpec, register


def _bill_rows(project) -> list[dict]:
    rows = []
    for bill in project.bills:
        data = bill.to_dict() if hasattr(bill, "to_dict") else dict(bill)
        rows.append(data)
    return rows


def _trade_item_rows(project) -> list[dict]:
    """取工种列表的 dict 形式。

    GUI 走的是 project_data（已序列化）→ trade_items 是 dict；这里保持一致，
    避免两条路径吃不同形态的输入而出现结果差异。
    """
    rows = []
    for item in project.trade_items:
        rows.append(item.to_dict() if hasattr(item, "to_dict") else dict(item))
    return rows


def _bill_list(args: argparse.Namespace) -> dict:
    project = require_project(args.uuid)
    rows = _bill_rows(project)
    # project_total 是项目整体金额（不受 --orphan-only 影响）；下面的 total
    # 则按本次实际输出的行重新累加，避免筛选后 total 与结果对不上。
    calculations, project_total, _error_count = summarize_bill_calculations(
        rows, _trade_item_rows(project), op_map()
    )

    items = []
    shown_total = Decimal("0")
    shown_error_count = 0
    for row, calc in zip(rows, calculations, strict=False):
        if args.orphan_only and not calc.orphan:
            continue
        shown_total += Decimal(str(calc.total))
        if calc.formula_error:
            shown_error_count += 1
        item = {
            "id": row.get("id", ""),
            "content": row.get("content", ""),
            "canonical": calc.canonical,
            "note": row.get("note", ""),
            "trade_item_id": row.get("trade_item_id", ""),
            "category": calc.category,
            "name": calc.name,
            "work_date_type": row.get("work_date_type", ""),
            "work_date_start": row.get("work_date_start", ""),
            "work_date_end": row.get("work_date_end", ""),
            "record_time": row.get("record_time", ""),
            "total": calc.total,
            "orphan": calc.orphan,
            "formula_error": calc.formula_error,
            "reviewed": bool(row.get("reviewed", False)),
        }
        items.append(item)

    # total / count 均针对"本次实际输出的行"。
    return {
        "uuid": project.project_uuid,
        "name": project.name,
        "count": len(items),
        "total": float(shown_total),
        "project_total": project_total,
        # 与 GUI 共用公式解析错误标记；零金额本身不是错误。
        "formula_error_count": shown_error_count,
        "bills": items,
    }


def _bill_summary(args: argparse.Namespace) -> dict:
    project = require_project(args.uuid)
    rows = _bill_rows(project)
    calculations, total, error_count = summarize_bill_calculations(
        rows, _trade_item_rows(project), op_map()
    )

    by_category: dict[str, Decimal] = {}
    by_trade_item: dict[str, dict] = {}
    orphan_total = Decimal("0")
    orphan_count = 0

    for calc in calculations:
        by_category[calc.category] = by_category.get(calc.category, Decimal("0")) + as_decimal(calc.total)
        key = calc.name or "（未命名）"
        bucket = by_trade_item.setdefault(
            key,
            {
                "name": key,
                "category": calc.category,
                "total": Decimal("0"),
                "count": 0,
                "unit_price": calc.billing.unit_price,
                "unit": calc.billing.unit,
            },
        )
        bucket["total"] += as_decimal(calc.total)
        bucket["count"] += 1
        if calc.orphan:
            orphan_total += as_decimal(calc.total)
            orphan_count += 1

    return {
        "uuid": project.project_uuid,
        "name": project.name,
        "status": project.status,
        "bill_count": len(rows),
        "total": total,
        "formula_error_count": error_count,
        "orphan_count": orphan_count,
        "orphan_total": float(orphan_total),
        "by_category": [
            {"category": key, "total": float(value)} for key, value in by_category.items()
        ],
        "by_trade_item": [{**r, "total": float(r["total"])}
                          for r in sorted(by_trade_item.values(), key=lambda r: -r["total"])],
    }


register(
    CommandSpec(
        name="bill.list",
        help="列出项目账单及每行合计",
        handler=_bill_list,
        args=(
            ArgSpec(name="uuid", help="项目 UUID", kind="positional"),
            ArgSpec(name="orphan_only", help="仅显示孤儿账单", type="flag"),
        ),
        examples=(
            "cpa bill.list <uuid> --json",
            "cpa bill.list <uuid> --orphan-only --json",
        ),
    )
)

register(
    CommandSpec(
        name="bill.summary",
        help="按分类 / 工作类型汇总金额",
        handler=_bill_summary,
        args=(ArgSpec(name="uuid", help="项目 UUID", kind="positional"),),
        examples=("cpa bill.summary <uuid> --json",),
    )
)


def _guard(_: InvalidArgument) -> None:  # pragma: no cover
    return None
