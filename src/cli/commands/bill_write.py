"""`bill` 写入命令：添加、修改、删除账单。

并发安全：写入前经 guard.ensure_gui_not_running()，之后统一通过
project_manager.update_project 落盘（内部自带写锁 + 备份策略）。
"""

from __future__ import annotations

import argparse
from datetime import datetime

from ...bill import Bill
from ...bill_recompute import calculate_bill
from ...project_status import ProjectStatus
from ...trade_item_id import compute_bill_id
from .. import common
from ..common import op_map, require_project
from ..errors import InvalidArgument, ProjectNotFound
from ..guard import ensure_gui_not_running
from ..registry import ArgSpec, CommandSpec, register

_DATE_TYPES = ("无时间", "单个时间", "起止时间")


def _trade_item_index(project) -> dict:
    index = {}
    for item in project.trade_items:
        getter = getattr(item, "get", None)
        item_id = getter("id") if callable(getter) else getattr(item, "id", None)
        if item_id:
            index[str(item_id)] = item
    return index


def _validate_date_args(args: argparse.Namespace) -> dict:
    date_type = args.work_date_type or "无时间"
    if date_type not in _DATE_TYPES:
        raise InvalidArgument(
            f"未知日期类型: {date_type}", details={"allowed": list(_DATE_TYPES)}
        )
    start = args.date_start or ""
    end = args.date_end or ""
    if date_type == "无时间" and (start or end):
        raise InvalidArgument("日期类型为「无时间」时不应传 --date-start/--date-end")
    if date_type == "单个时间" and not start:
        raise InvalidArgument("日期类型为「单个时间」时需要 --date-start")
    if date_type == "起止时间" and not (start and end):
        raise InvalidArgument(
            "日期类型为「起止时间」时需要同时传 --date-start 与 --date-end"
        )
    return {"type": date_type, "start": start, "end": end}


def _find_bill(project, bill_id: str) -> Bill:
    for bill in project.bills:
        if getattr(bill, "id", "") == bill_id:
            return bill
    raise ProjectNotFound(
        f"账单不存在: {bill_id}",
        details={"uuid": project.project_uuid, "bill_id": bill_id},
    )


def _bill_view(project, bill: Bill) -> dict:
    """单条账单的展示结构（含按当前单价重算的合计）。"""
    data = bill.to_dict()
    trade_items = [
        item.to_dict() if hasattr(item, "to_dict") else dict(item)
        for item in project.trade_items
    ]
    calc = calculate_bill(data, trade_items, op_map())
    return {
        "id": data.get("id", ""),
        "content": data.get("content", ""),
        "canonical": calc.canonical,
        "note": data.get("note", ""),
        "trade_item_id": data.get("trade_item_id", ""),
        "category": calc.category,
        "name": calc.name,
        "work_date_type": data.get("work_date_type", ""),
        "work_date_start": data.get("work_date_start", ""),
        "work_date_end": data.get("work_date_end", ""),
        "record_time": data.get("record_time", ""),
        "total": calc.total,
        "orphan": calc.orphan,
        "formula_error": calc.formula_error,
        "reviewed": bool(data.get("reviewed", False)),
    }


def _bill_add(args: argparse.Namespace) -> dict:
    ensure_gui_not_running()
    project = require_project(args.uuid)
    # 与 GUI 一致的冻结规则：ProjectStatus.is_editable（已完成项目不可改）
    if not ProjectStatus.from_value(project.status).is_editable:
        raise InvalidArgument(
            f"项目「{project.name}」已完成，不可修改账单。"
            "如需编辑请先改状态：cpa project.status <uuid> editing",
            details={"uuid": project.project_uuid, "status": project.status},
        )

    trade_item_id = (args.trade_item or "").strip()
    index = _trade_item_index(project)
    if trade_item_id and trade_item_id not in index:
        raise InvalidArgument(
            f"工作类型不存在: {trade_item_id}",
            details={"available": sorted(index.keys())},
        )
    if not trade_item_id:
        # 允许孤儿账单（GUI 支持：删除工作类型后保留快照金额），
        # 但必须显式说明，避免静默产生孤儿数据。
        if not args.allow_orphan:
            raise InvalidArgument(
                "未指定 --trade-item。若确实要登记不关联工作类型的账单，"
                "请加 --allow-orphan。",
                details={"available": sorted(index.keys())},
            )
        trade_item_id = ""

    content = args.content
    if content is None:
        content = ""
    note = args.note or ""
    dates = _validate_date_args(args)
    # 与 GUI 账单编辑器（dialogs/edit_bill.py）保持完全一致的本地时间格式。
    # 这里刻意不用 tz-aware 时间：项目全库统一存本地墙上时间，若只在此处
    # 引入时区，CLI 生成的 record_time 会与 GUI 写入的无法比较/去重。
    record_time = args.record_time or datetime.now().strftime(  # noqa: DTZ005
        "%Y-%m-%d %H:%M:%S"
    )

    bill_id = compute_bill_id(trade_item_id, content, record_time)
    if any(getattr(b, "id", "") == bill_id for b in project.bills):
        raise InvalidArgument(
            "已存在相同内容与时间的账单（ID 冲突）",
            details={"bill_id": bill_id},
        )

    bill = Bill(
        id=bill_id,
        trade_item_id=trade_item_id,
        content=content,
        note=note,
        work_date_type=dates["type"],
        work_date_start=dates["start"],
        work_date_end=dates["end"],
        record_time=record_time,
    )
    project.bills.append(bill)
    common.project_manager.update_project(args.uuid, project)

    refreshed = require_project(args.uuid)
    result = _bill_view(refreshed, _find_bill(refreshed, bill_id))
    result["uuid"] = refreshed.project_uuid
    return result


def _apply_bill_edits(bill: Bill, args: argparse.Namespace) -> bool:
    """把命令行传入的字段写回 bill，返回是否有改动。"""
    changed = False
    if args.content is not None and args.content != bill.content:
        bill.content = args.content
        changed = True
    if args.note is not None and args.note != bill.note:
        bill.note = args.note
        changed = True
    if args.reviewed is not None:
        wanted = bool(args.reviewed)
        if wanted != bool(bill.reviewed):
            bill.reviewed = wanted
            changed = True

    date_touched = any(
        value is not None
        for value in (args.work_date_type, args.date_start, args.date_end)
    )
    if date_touched:
        dates = _validate_date_args(args)
        if (
            dates["type"] != bill.work_date_type
            or dates["start"] != bill.work_date_start
            or dates["end"] != bill.work_date_end
        ):
            bill.work_date_type = dates["type"]
            bill.work_date_start = dates["start"]
            bill.work_date_end = dates["end"]
            changed = True
    return changed


def _bill_update(args: argparse.Namespace) -> dict:
    ensure_gui_not_running()
    project = require_project(args.uuid)
    bill = _find_bill(project, args.bill_id)

    if not _apply_bill_edits(bill, args):
        result = _bill_view(project, bill)
        result["uuid"] = project.project_uuid
        result["changed"] = False
        return result

    common.project_manager.update_project(args.uuid, project)
    refreshed = require_project(args.uuid)
    result = _bill_view(refreshed, _find_bill(refreshed, args.bill_id))
    result["uuid"] = refreshed.project_uuid
    result["changed"] = True
    return result


def _bill_remove(args: argparse.Namespace) -> dict:
    ensure_gui_not_running()
    project = require_project(args.uuid)
    bill = _find_bill(project, args.bill_id)
    removed = _bill_view(project, bill)

    project.bills = [b for b in project.bills if getattr(b, "id", "") != args.bill_id]
    common.project_manager.update_project(args.uuid, project)

    return {
        "uuid": project.project_uuid,
        "removed": removed,
        "remaining": len(project.bills),
    }


register(
    CommandSpec(
        name="bill.add",
        help="添加账单记录",
        handler=_bill_add,
        read_only=False,
        args=(
            ArgSpec(name="uuid", help="项目 UUID", kind="positional"),
            ArgSpec(name="content", help="算式内容，如 3*4+5", kind="positional"),
            ArgSpec(name="trade_item", help="工作类型 ID（见 project.show）"),
            ArgSpec(name="note", help="备注"),
            ArgSpec(
                name="work_date_type",
                help="日期类型：无时间/单个时间/起止时间",
                default="无时间",
            ),
            ArgSpec(name="date_start", help="开始日期或单日期"),
            ArgSpec(name="date_end", help="结束日期（起止时间时必填）"),
            ArgSpec(name="record_time", help="记录时间（默认当前时间）"),
            ArgSpec(name="allow_orphan", help="允许不关联工作类型", type="flag"),
        ),
        examples=(
            "cpa bill.add <uuid> '3*4+5' --trade-item ti_wall --json",
            "cpa bill.add <uuid> '2+1' --trade-item ti_wall --note '三份' --json",
        ),
    )
)

register(
    CommandSpec(
        name="bill.update",
        help="修改账单（只改传入的字段）",
        handler=_bill_update,
        read_only=False,
        args=(
            ArgSpec(name="uuid", help="项目 UUID", kind="positional"),
            ArgSpec(name="bill_id", help="账单 ID", kind="positional"),
            ArgSpec(name="content", help="新的算式内容"),
            ArgSpec(name="note", help="新的备注"),
            ArgSpec(name="work_date_type", help="新的日期类型"),
            ArgSpec(name="date_start", help="新的开始日期"),
            ArgSpec(name="date_end", help="新的结束日期"),
            ArgSpec(name="reviewed", help="标记为已审核", type="flag"),
        ),
        examples=("cpa bill.update <uuid> <bill-id> --content '5*5' --json",),
    )
)

register(
    CommandSpec(
        name="bill.remove",
        help="删除账单",
        handler=_bill_remove,
        read_only=False,
        args=(
            ArgSpec(name="uuid", help="项目 UUID", kind="positional"),
            ArgSpec(name="bill_id", help="账单 ID", kind="positional"),
        ),
        examples=("cpa bill.remove <uuid> <bill-id> --json",),
    )
)
