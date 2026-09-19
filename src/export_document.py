"""Build export documents independently of Qt widgets."""
from datetime import datetime
from .billing import read_billing
from .bill_recompute import prepare_bill_calculations
from .calculator import to_canonical, to_display, MathParseError
from .money import sum_money
from .theme_tokens import DANGER_FG as SYSTEM_RED, TEXT_PRIMARY


def _category_name(category) -> str:
    if hasattr(category, "name"):
        return category.name
    if isinstance(category, dict):
        return category.get("name", "")
    return str(category)


def _category_id(category) -> str:
    if hasattr(category, "id"):
        return category.id
    if isinstance(category, dict):
        return category.get("id", "")
    return ""


def _format_project_date(p: dict) -> str:
    dt = p.get("project_date_type", "无时间")
    if dt == "无时间":
        return ""
    if dt == "单个时间":
        return p.get("project_date_start", "")
    if dt == "起止时间":
        s = p.get("project_date_start", "")
        e = p.get("project_date_end", "")
        if s and e:
            return f"{s} ~ {e}"
        return s or e
    return ""


def _format_bill_date(b: dict) -> str:
    dt = b.get("work_date_type")
    if not dt:
        return b.get("work_date_start", "")
    if dt == "无时间":
        return ""
    if dt == "单个时间":
        return b.get("work_date_start", "")
    if dt == "起止时间":
        s = b.get("work_date_start", "")
        e = b.get("work_date_end", "")
        if s and e:
            return f"{s} ~ {e}"
        return s or e
    return ""


def _format_formula(content_raw: str, op_map: dict, extra_outer_layers: int = 0) -> str:
    if not content_raw:
        return ""
    try:
        canonical = to_canonical(content_raw, op_map)
        return to_display(canonical, extra_outer_layers=extra_outer_layers)
    except MathParseError:
        return content_raw


def build_export_blocks(project: dict, op_map: dict, ec, export_time=None):
    """纯函数：把项目 + 账单 + 导出设置渲染为图片 block 列表（Qt 侧复制品）。

    逻辑与 Tk 版 build_export_blocks 保持一致（不含任何 UI 依赖），
    便于无头测试；返回 (blocks, total_amount)。
    """
    if export_time is None:
        export_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    p = project or {}
    bills = p.get("bills", []) or []
    trade_items = p.get("trade_items", []) or []
    calculations = prepare_bill_calculations(bills, trade_items, op_map)

    blocks: list[dict] = []

    blocks.append({"text": f"{p.get('name', '')}", "style": "title"})
    if ec.show_project_date or ec.show_project_created_at:
        proj_date_text = _format_project_date(p)
        if ec.show_project_date and proj_date_text:
            blocks.append({"text": f"项目日期：{proj_date_text}",
                           "style": "small", "color": ec.text_colors.muted})
        if ec.show_project_created_at:
            blocks.append({"text": f"创建时间：{p.get('created_at', 'N/A')}",
                           "style": "small", "color": ec.text_colors.muted})
    if ec.show_export_time:
        blocks.append({"text": f"导出时间：{export_time}",
                       "style": "small", "color": ec.text_colors.muted})
    blocks.append({"style": "separator"})

    # ── 价目表 ──
    if ec.price_list_settings.visible and trade_items:
        blocks.append({"text": "【价目表】", "style": "heading"})
        cats = list(p.get("category_order", []) or [])
        cat_names = {_category_name(c) for c in cats}
        cat_ids = {_category_id(c) for c in cats if _category_id(c)}
        for ti in trade_items:
            ti_cat = ti.get("category", "")
            ti_cat_id = ti.get("category_id", "")
            if ti_cat and ti_cat not in cat_names:
                cats.append(ti_cat)
                cat_names.add(ti_cat)
            elif not ti_cat and ti_cat_id and ti_cat_id not in cat_ids:
                cats.append({"id": ti_cat_id, "name": ti_cat_id})
                cat_ids.add(ti_cat_id)

        cat_id_by_name = {_category_name(c): _category_id(c) for c in cats}
        for cat in cats:
            cat_name = _category_name(cat)
            cat_id = _category_id(cat) or cat_id_by_name.get(cat_name, "")
            cat_items = [
                ti for ti in trade_items
                if ti.get("category") == cat_name or ti.get("category_id") == cat_id
            ]
            if not cat_items and not ec.price_list_settings.show_empty_categories:
                continue
            blocks.append({"text": f"  {cat_name}", "style": "body",
                           "color": ec.text_colors.muted})
            for ti in cat_items:
                billing = read_billing(ti)
                if not billing.is_per_unit and not ec.price_list_settings.show_no_unit_items:
                    continue
                if billing.is_per_unit:
                    if ec.price_list_settings.align_columns:
                        blocks.append({
                            "style": "price_list_row",
                            "color": ec.text_colors.muted,
                            "columns": [
                                {"text": ti.get("name", ""),
                                 "width": ec.price_list_settings.name_width, "align": "left"},
                                {"text": "单价", "width": 4, "align": "left"},
                                {"text": f"{billing.unit_price:.2f}",
                                 "width": ec.price_list_settings.price_width, "align": "right"},
                                {"text": billing.unit, "width": 6, "align": "left"},
                            ],
                            "indent": 24,
                        })
                        continue
                    blocks.append({"text": f"    {ti.get('name', '')}    "
                                           f"单价 {billing.unit_price:.2f} {billing.unit}",
                                   "style": "small", "color": ec.text_colors.muted})
                else:
                    if ec.price_list_settings.align_columns:
                        blocks.append({
                            "style": "price_list_row",
                            "color": ec.text_colors.muted,
                            "columns": [
                                {"text": ti.get("name", ""),
                                 "width": ec.price_list_settings.name_width, "align": "left"},
                                {"text": "无单价", "width": 10, "align": "left"},
                            ],
                            "indent": 24,
                        })
                        continue
                    blocks.append({"text": f"    {ti.get('name', '')}    无单价",
                                   "style": "small", "color": ec.text_colors.muted})
        blocks.append({"style": "separator"})

    # ── 账单明细 ──
    blocks.append({"text": "【账单明细】", "style": "heading"})
    total = sum_money(calc.total for calc in calculations)
    for i, (b, calc) in enumerate(zip(bills, calculations), 1):
        content = b.get("content", "")
        note = b.get("note", "")
        date = _format_bill_date(b)
        record_time = b.get("record_time", "")
        category, name = calc.category, calc.name
        billing = calc.billing
        total_val = calc.total
        orphan = calc.orphan

        total_str = f"￥{total_val:.2f}" if isinstance(total_val, (int, float)) else "错误"

        name_prefix = "⚠ " if orphan else ""
        name_suffix = "（已删除）" if orphan else ""
        if ec.strip_category:
            display = f"{name_prefix}{name}{name_suffix}"
        else:
            display = f"{name_prefix}{category} - {name}{name_suffix}"
        if ec.append_note_to_item_title and note:
            display = f"{display} - {note}"
        blocks.append({"text": f"# {i}  {display}", "style": "body",
                       "color": SYSTEM_RED if orphan else TEXT_PRIMARY})

        if calc.canonical:
            formula_text = to_display(
                calc.canonical,
                extra_outer_layers=1 if billing.is_per_unit else 0,
            )
        else:
            formula_text = _format_formula(content, op_map)
        if billing.is_per_unit and formula_text:
            formula_text = f"{formula_text} × ￥{billing.unit_price:.2f}"
        blocks.append({"text": f"  公式：{formula_text}", "style": "body",
                       "color": ec.text_colors.formula})
        blocks.append({"text": f"  金额：{total_str}", "style": "body",
                       "color": ec.text_colors.amount})

        if date:
            date_info = f"  工作日期：{date}"
            if record_time and ec.show_record_time:
                date_info += f"    （录入：{record_time}）"
            blocks.append({"text": date_info, "style": "small",
                           "color": ec.text_colors.muted})

        if note and not ec.append_note_to_item_title:
            blocks.append({"text": f"  备注：{note}", "style": "small",
                           "color": ec.text_colors.muted})
        blocks.append({"style": "blank"})

    blocks.append({"style": "separator"})
    blocks.append({"text": f"合计：￥{total:.2f}", "style": "heading",
                   "color": ec.text_colors.amount})
    return blocks, total


