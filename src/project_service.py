"""Shared project mutations; no GUI, CLI or persistence dependencies."""

from copy import deepcopy
from datetime import date

from .bill import Bill
from .bill_recompute import calculate_bill, prepare_bill_calculations
from .billing import Billing, read_billing, write_billing
from .calculator import MathParseError, evaluate_decimal, to_canonical
from .money import validate_price
from .project import Project
from .project_status import ProjectStatus
from .trade_item import TradeItem
from .trade_item_id import compute_bill_id, ensure_trade_item_id


class ValidationError(ValueError):
    """User-correctable domain validation failure."""


def require_editable(project: Project) -> None:
    if not ProjectStatus.from_value(project.status).is_editable:
        raise ValidationError("项目已完成，请先改为编辑中再进行此操作")


def validate_formula(content: str, op_map: dict) -> str:
    content = (content or "").strip()
    if not content:
        raise ValidationError("请输入计算公式")
    try:
        evaluate_decimal(to_canonical(content, op_map))
    except MathParseError as exc:
        raise ValidationError(str(exc)) from exc
    return content


def update_trade_fields(item, *, name, category, has_unit, unit_price, unit) -> None:
    """Validate everything before mutating the live object."""
    name = (name or "").strip()
    if not name:
        raise ValidationError("工作类型名称不能为空")
    try:
        billing = Billing(
            has_unit=has_unit,
            unit_price=validate_price(unit_price) if has_unit else 0,
            unit=(unit or "").strip(),
        )
    except ValueError as exc:
        raise ValidationError(str(exc)) from exc
    item["name"] = name
    # Reset stale category IDs; Project resolves the new name explicitly.
    if item.get("category", "") != (category or "").strip():
        item["category_id"] = ""
    item["category"] = (category or "").strip()
    ensure_trade_item_id(item)
    write_billing(item, billing)


def save_trade(project: Project, data) -> TradeItem:
    require_editable(project)
    payload = dict(data.to_dict() if hasattr(data, "to_dict") else data)
    # TradeItem.to_dict() intentionally writes the v3 ID-based schema and omits the
    # legacy category name. Keep the in-memory name long enough to resolve/ensure
    # its category ID before persistence.
    if hasattr(data, "category"):
        payload["category"] = data.category
    update_trade_fields(
        payload,
        name=payload.get("name"),
        category=payload.get("category", ""),
        has_unit=payload.get("has_unit", True),
        unit_price=payload.get("unit_price", 1),
        unit=payload.get("unit", ""),
    )
    candidate = TradeItem.from_dict(payload)
    candidate.category_id = project.ensure_category(candidate.category)
    for index, item in enumerate(project.trade_items):
        if item.id == candidate.id:
            project.trade_items[index] = candidate
            break
    else:
        project.trade_items.append(candidate)
    return candidate


def freeze_bill(bill, item, total: float) -> None:
    billing = read_billing(item)
    bill["frozen_snapshot"] = {
        "name": item.get("name", ""),
        "category": item.get("category", ""),
        **billing.to_dict(),
    }
    bill["frozen_total"] = total
    bill["trade_item_id"] = ""
    bill["_needs_attention"] = True


def remove_trades(project: Project, ids: set[str], op_map: dict) -> None:
    require_editable(project)
    bill_data = [bill.to_dict() for bill in project.bills]
    trade_data = [item.to_dict() for item in project.trade_items]
    calculations = prepare_bill_calculations(bill_data, trade_data, op_map)
    for bill, calc in zip(project.bills, calculations, strict=True):
        if bill.trade_item_id in ids and calc.trade_item is not None:
            freeze_bill(bill, calc.trade_item, calc.total)
    project.replace_trade_items(
        [item for item in project.trade_items if item.id not in ids]
    )


def associate_bill(
    updated: dict, existing, item, trade_items: list, op_map: dict
) -> None:
    if item is not None:
        updated["trade_item_id"] = ensure_trade_item_id(item)
        for key in ("frozen_snapshot", "frozen_total", "_needs_attention"):
            updated.pop(key, None)
        return
    calc = calculate_bill(
        {**updated, "trade_item_id": existing.get("trade_item_id", "")},
        trade_items,
        op_map,
    )
    updated["trade_item_id"] = ""
    if calc.trade_item is not None:
        freeze_bill(updated, calc.trade_item, calc.total)
    else:
        for key in ("frozen_snapshot", "frozen_total", "_needs_attention"):
            if existing.get(key) is not None:
                updated[key] = deepcopy(existing.get(key))


def save_bill(project: Project, data, op_map: dict) -> Bill:
    payload = data.to_dict() if hasattr(data, "to_dict") else dict(data)
    payload["content"] = validate_formula(payload.get("content", ""), op_map)
    validate_dates(
        payload.get("work_date_type", "无时间"),
        payload.get("work_date_start", ""),
        payload.get("work_date_end", ""),
    )
    identifier = payload.get("id")
    existing = (
        next((b for b in project.bills if b.id == identifier), None)
        if identifier
        else None
    )
    if existing is None:
        require_editable(project)
    if not identifier:
        payload["id"] = compute_bill_id(
            payload.get("trade_item_id", ""),
            payload["content"],
            payload.get("record_time", ""),
        )
        if any(b.id == payload["id"] for b in project.bills):
            raise ValidationError("已存在相同内容与时间的账单（ID 冲突）")
    bill = Bill.from_dict(payload)
    if existing is None:
        project.bills.append(bill)
    else:
        project.bills[project.bills.index(existing)] = bill
    return bill


def remove_bill(project: Project, identifier: str) -> None:
    require_editable(project)
    project.bills = [bill for bill in project.bills if bill.id != identifier]


def validate_dates(kind: str, start: str = "", end: str = "") -> dict:
    if kind not in ("无时间", "单个时间", "起止时间"):
        raise ValidationError(f"未知日期类型：{kind}")
    if kind == "无时间" and (start or end):
        raise ValidationError("无时间类型不能填写开始或结束日期")
    if kind == "单个时间" and (not start or end):
        raise ValidationError("单个时间需要开始日期，且不能填写结束日期")
    if kind == "起止时间" and not (start and end):
        raise ValidationError("起止时间需要同时填写开始与结束日期")
    try:
        parsed_start = date.fromisoformat(start) if start else None
        parsed_end = date.fromisoformat(end) if end else None
    except ValueError as exc:
        raise ValidationError("日期必须是有效的 YYYY-MM-DD 日期") from exc
    if parsed_start and parsed_end and parsed_start > parsed_end:
        raise ValidationError("结束日期不能早于开始日期")
    return {"type": kind, "start": start, "end": end}
