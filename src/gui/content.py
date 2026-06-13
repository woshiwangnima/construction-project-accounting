"""主内容区域（账单记录 + 工作类型管理）"""

import os
import tkinter as tk
from tkinter import ttk, messagebox, filedialog
from datetime import datetime
from typing import Optional

from .theme import (
    APP_BG, ACCENT, TEXT_PRIMARY, TEXT_SECONDARY, BORDER, HIGHLIGHT_BG,
    FONT_TITLE, FONT_HEADING, FONT_SUBHEADING, FONT_BODY, FONT_BODY_BOLD,
    FONT_SMALL,
)
from .widgets import _make_btn, _set_btn_state, _input_entry, ScrollableFrame, TooltipCarousel
from .widgets.reorder import move_item, reorder_subset_by_ids
from .dialogs.edit_bill import EditBillDialog
from .dialogs.edit_trade import EditTradeItemDialog
from .editability import EditabilityPolicy
from ..logger import logger
from ..project_manager import (
    get_project, update_project, _load_default_items, _load_default_categories,
)
from ..project_status import ProjectStatus
from ..config_loader import load_user, save_user, load_app
from ..export_config import ExportDefaults
from ..image_output import save_styled_image
from ..calculator import to_canonical, to_display, MathParseError
from ..billing import read_billing
from ..billing_resolver import (
    resolve_billing, resolve_label, resolve_trade_item, is_orphan, orphan_bills,
)
from ..bill_recompute import recompute_bill_total
from ..bill_review import set_bill_reviewed, apply_bulk_review
from ..paste_actions import (
    paste_bill, paste_trade_item, unique_category_after_paste,
)
from .clipboard import AppClipboard


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


def _category_maps(project: dict) -> tuple[dict[str, str], dict[str, str]]:
    id_to_name = {}
    name_to_id = {}
    for category in (project or {}).get("category_order", []) or []:
        cid = _category_id(category)
        name = _category_name(category)
        if cid:
            id_to_name[cid] = name
        if name:
            name_to_id[name] = cid
    return id_to_name, name_to_id


def _trade_item_category_name(item: dict, project: dict) -> str:
    if item.get("category"):
        return item.get("category", "")
    id_to_name, _ = _category_maps(project)
    return id_to_name.get(item.get("category_id", ""), item.get("category_id", ""))


def _project_category_names(project: dict) -> list[str]:
    names = [_category_name(c) for c in (project or {}).get("category_order", []) or []]
    for item in (project or {}).get("trade_items", []) or []:
        name = _trade_item_category_name(item, project)
        if name and name not in names:
            names.append(name)
    return names


def _category_order_for_names(project: dict, names: list[str]) -> list[dict | str]:
    by_name = {_category_name(c): c for c in (project or {}).get("category_order", []) or []}
    return [by_name.get(name, name) for name in names]


def _default_worker_data() -> tuple[list[dict], list[dict]]:
    categories = [c.to_dict() for c in _load_default_categories()]
    items = _load_default_items()
    if not categories:
        seen = {}
        for item in items:
            name = item.get("category", "") or item.get("category_id", "")
            if name and name not in seen:
                seen[name] = item.get("category_id", "")
        categories = [{"id": cid, "name": name} for name, cid in seen.items()]
    return categories, items


def _format_formula(content_raw: str, op_map: dict, extra_outer_layers: int = 0) -> str:
    """将用户原始公式转为标准化展示形式；解析失败时回落显示原始字符串。"""
    if not content_raw:
        return ""
    try:
        canonical = to_canonical(content_raw, op_map)
        return to_display(canonical, extra_outer_layers=extra_outer_layers)
    except MathParseError:
        return content_raw


def build_export_blocks(project: dict, op_map: dict, ec,
                        export_time: str | None = None) -> tuple[list[dict], float]:
    """纯函数：把项目和账单数据 + 导出设置，渲染为图片 block 列表与总金额。

    与 GUI 无关，便于测试。`export_time` 默认 `None` → 用 `datetime.now()`。
    返回 `(blocks, total_amount)`。
    """
    if export_time is None:
        export_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    p = project
    bills = p.get("bills", [])
    trade_items = p.get("trade_items", [])

    blocks: list[dict] = []

    # 项目头部信息
    blocks.append({"text": f"{p.get('name', '')}", "style": "title"})
    if ec.show_project_date:
        proj_date_text = _format_project_date(p)
        if proj_date_text:
            blocks.append({"text": f"项目日期：{proj_date_text}", "style": "small", "color": ec.text_colors.muted})
        blocks.append({"text": f"创建时间：{p.get('created_at', 'N/A')}", "style": "small", "color": ec.text_colors.muted})
    if ec.show_export_time:
        blocks.append({"text": f"导出时间：{export_time}", "style": "small", "color": ec.text_colors.muted})
    blocks.append({"style": "separator"})

    # 工作类型价目表
    if ec.price_list_settings.visible:
        if trade_items:
            blocks.append({"text": "【价目表】", "style": "heading"})
            cat_order = p.get("category_order", [])
            cats = list(cat_order) if cat_order else []
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

            cat_id_by_name = {_category_name(c): _category_id(c) for c in cat_order}
            for cat in cats:
                cat_name = _category_name(cat)
                cat_id = _category_id(cat) or cat_id_by_name.get(cat_name, "")
                cat_items = [ti for ti in trade_items if ti.get("category") == cat_name or ti.get("category_id") == cat_id]
                if not cat_items and not ec.price_list_settings.show_empty_categories:
                    continue
                blocks.append({"text": f"  {cat_name}", "style": "body", "color": ec.text_colors.muted})
                for ti in cat_items:
                    name = ti.get("name", "")
                    billing = read_billing(ti)
                    if not billing.is_per_unit and not ec.price_list_settings.show_no_unit_items:
                        continue
                    if billing.is_per_unit:
                        if ec.price_list_settings.align_columns:
                            blocks.append({
                                "style": "price_list_row",
                                "color": ec.text_colors.muted,
                                "columns": [
                                    {"text": name, "width": ec.price_list_settings.name_width, "align": "left"},
                                    {"text": "单价", "width": 4, "align": "left"},
                                    {"text": f"{billing.unit_price:.2f}", "width": ec.price_list_settings.price_width, "align": "right"},
                                    {"text": billing.unit, "width": 6, "align": "left"},
                                ],
                                "indent": 24,
                            })
                            continue
                        else:
                            line = f"    {name}    单价 {billing.unit_price:.2f} {billing.unit}"
                        blocks.append({"text": line, "style": "small", "color": ec.text_colors.muted})
                    else:
                        if ec.price_list_settings.align_columns:
                            blocks.append({
                                "style": "price_list_row",
                                "color": ec.text_colors.muted,
                                "columns": [
                                    {"text": name, "width": ec.price_list_settings.name_width, "align": "left"},
                                    {"text": "无单价", "width": 10, "align": "left"},
                                ],
                                "indent": 24,
                            })
                            continue
                        else:
                            line = f"    {name}    无单价"
                        blocks.append({"text": line, "style": "small", "color": ec.text_colors.muted})
            blocks.append({"style": "separator"})

    # 账单明细
    blocks.append({"text": "【账单明细】", "style": "heading"})

    total = 0.0
    for i, b in enumerate(bills, 1):
        content = b.get("content", "")
        note = b.get("note", "")
        date = _format_bill_date(b)
        record_time = b.get("record_time", "")
        # 实时 join：name/category/单价/合计
        category, name = resolve_label(b, trade_items)
        billing = resolve_billing(b, trade_items)
        total_val = recompute_bill_total(b, trade_items, op_map)
        orphan = is_orphan(b, trade_items)

        total_str = f"￥{total_val:.2f}" if isinstance(total_val, (int, float)) else "错误"
        if isinstance(total_val, (int, float)):
            total += total_val

        # 名称前缀：孤儿加 ⚠ + 「（已删除）」
        name_prefix = "⚠ " if orphan else ""
        name_suffix = "（已删除）" if orphan else ""

        if ec.strip_category:
            display = f"{name_prefix}{name}{name_suffix}"
        else:
            display = f"{name_prefix}{category} - {name}{name_suffix}"
        if ec.append_note_to_item_title and note:
            display = f"{display} - {note}"
        blocks.append({"text": f"# {i}  {display}", "style": "body",
                      "color": "#c0392b" if orphan else "#000000"})

        if billing.is_per_unit:
            formula_text = _format_formula(content, op_map, extra_outer_layers=1)
            if formula_text:
                formula_text = f"{formula_text} × ￥{billing.unit_price:.2f}"
        else:
            formula_text = _format_formula(content, op_map)
        blocks.append({"text": f"  公式：{formula_text}", "style": "body", "color": ec.text_colors.formula})

        blocks.append({"text": f"  金额：{total_str}", "style": "body", "color": ec.text_colors.amount})

        if date:
            date_info = f"  工作日期：{date}"
            if record_time and ec.show_record_time:
                date_info += f"    （录入：{record_time}）"
            blocks.append({"text": date_info, "style": "small", "color": ec.text_colors.muted})

        if note and not ec.append_note_to_item_title:
            blocks.append({"text": f"  备注：{note}", "style": "small", "color": ec.text_colors.muted})

        blocks.append({"style": "blank"})

    blocks.append({"style": "separator"})
    blocks.append({"text": f"合计：￥{total:.2f}", "style": "heading", "color": ec.text_colors.amount})
    return blocks, total


def _format_bill_date(b: dict) -> str:
    """根据 bill 的 work_date_type 三态渲染为简短文本。无时间时返回空串。"""
    dt = b.get("work_date_type")
    if not dt:
        return b.get("work_date_start", "")
    if dt == "无时间":
        return ""
    if dt == "单个时间":
        s = b.get("work_date_start", "")
        return s
    if dt == "起止时间":
        s = b.get("work_date_start", "")
        e = b.get("work_date_end", "")
        if s and e:
            return f"{s} ~ {e}"
        return s or e
    return ""


# ── 账单管理（bills）列宽配置 ─────────────────────────────────────────────
# 权重（weights）总和 = 1.0；窗口缩放时按比例自动重算像素宽度。
# 存储位置：项目文件 bill_column_widths（用户调过的列）→ app_config 默认。
# 兼容旧字段名"数量"（作为"公式"的别名）—— 见 resolve_bill_column_weights。
BILLS_COLUMNS = ("#", "审核", "工作内容", "公式", "单价", "金额", "备注", "日期", "操作")
BILLS_MIN_WIDTH = 40
BILLS_DEFAULT_WEIGHTS = {
    "#": 0.0526315789,
    "审核": 0.05,
    "工作内容": 0.1394736842,
    "公式": 0.1263157895,
    "单价": 0.1263157895,
    "金额": 0.1263157895,
    "备注": 0.1684210526,
    "日期": 0.1263157895,
    "操作": 0.0842105263,
}

# ── 工作类型（worker）表格列宽配置 ─────────────────────────────────────
# 与 bills 不同：worker 是 ttk.Treeview，没有"操作"列；列宽用户可调（拖 heading 边界），
# 存到项目文件 worker_column_widths。
WORKER_COLUMNS = ("名称", "单价", "单位", "计费类型", "操作")
WORKER_MIN_WIDTH = 60
WORKER_DEFAULT_WEIGHTS = {
    "名称": 0.3571428571,    # 5/14
    "单价": 0.2142857143,    # 3/14
    "单位": 0.2142857143,
    "计费类型": 0.2142857143,
    "操作": 0.12,
}

CATEGORY_LIST_DEFAULT_WEIGHTS = {"name": 0.80, "count": 0.20}

def _category_list_weights():
    from ..config_loader import load_app
    cfg = load_app().get("list_column_weights", {}).get("category_list", {})
    return {
        "name": cfg.get("name", CATEGORY_LIST_DEFAULT_WEIGHTS["name"]),
        "count": cfg.get("count", CATEGORY_LIST_DEFAULT_WEIGHTS["count"]),
    }


def _safe_positive_float(v) -> float | None:
    try:
        x = float(v)
        if x > 0:
            return x
    except (TypeError, ValueError):
        pass
    return None


def resolve_bill_column_weights(project_data: dict) -> dict:
    """解析 bills 列的权重：项目保存值 → app_config 默认 → 模块级硬编码。

    返回的 dict 保证所有 BILLS_COLUMNS 都存在。**不归一化**：用户的权重就是用户
    的意图，原样保留。像素换算阶段（weights_to_pixels）会内部归一化。
    """
    saved = (project_data or {}).get("bill_column_widths", {}) or {}
    try:
        defaults = load_app().get("default_bill_column_widths", {}) or {}
    except Exception:
        defaults = {}

    result: dict[str, float] = {}
    for col in BILLS_COLUMNS:
        w = _safe_positive_float(saved.get(col))
        if w is not None:
            result[col] = w
            continue
        # 兼容旧字段名 "数量" → "公式"
        if col == "公式":
            w = _safe_positive_float(saved.get("数量"))
            if w is not None:
                result[col] = w
                continue
        w = _safe_positive_float(defaults.get(col))
        if w is not None:
            result[col] = w
            continue
        result[col] = BILLS_DEFAULT_WEIGHTS[col]
    logger.debug("resolve_bill_column_weights: saved=%s result=%s", saved, result)
    return result


def resolve_worker_column_weights(project_data: dict) -> dict:
    """解析 worker 表格列的权重：项目保存值 → app_config 默认 → 模块级硬编码。

    与 bills 同模式（多级 fallback）。字段名 `worker_column_widths`；app_config
    字段名 `default_worker_column_widths`。
    """
    saved = (project_data or {}).get("worker_column_widths", {}) or {}
    try:
        app_defaults = load_app().get("default_worker_column_widths", {}) or {}
    except Exception:
        app_defaults = {}

    result: dict[str, float] = {}
    for col in WORKER_COLUMNS:
        w = _safe_positive_float(saved.get(col))
        if w is not None:
            result[col] = w
            continue
        w = _safe_positive_float(app_defaults.get(col))
        if w is not None:
            result[col] = w
            continue
        result[col] = WORKER_DEFAULT_WEIGHTS[col]
    logger.debug("resolve_worker_column_weights: saved=%s result=%s", saved, result)
    return result


def weights_to_pixels(weights: dict, total_width: int,
                      min_width: int = BILLS_MIN_WIDTH) -> dict:
    """权重 → 像素宽度。每列至少 min_width。

    算法：先给每列 `min_width`（保证最小可读），剩余空间按权重分配。
    树太小时全给 min_width，超出由 Tk 滚动条兜底。
    """
    if total_width < 1 or not weights:
        return {}
    s = sum(weights.values())
    if s <= 0:
        return {}
    n = len(weights)
    min_total = min_width * n
    if total_width < min_total:
        return {c: min_width for c in weights}
    extra = total_width - min_total
    return {
        c: min_width + int(round(weights[c] / s * extra))
        for c in weights
    }


def pixels_to_weights(pixels: dict, total_width: int) -> dict | None:
    """像素 → 归一化权重（sum=1.0，10 位精度）。无效输入返回 None。"""
    if total_width < 1 or not pixels:
        return None
    s = sum(pixels.values())
    if s <= 0:
        return None
    return {c: round(p / s, 10) for c, p in pixels.items()}


def apply_bill_column_widths(tree, weights: dict,
                              min_width: int = BILLS_MIN_WIDTH,
                              total_width: int | None = None) -> bool:
    """按当前树宽把权重应用到所有列；返回是否成功应用。

    `total_width` 用于测试；None 时用 `tree.winfo_width()`。
    """
    if total_width is None:
        tree.update_idletasks()
        total_width = tree.winfo_width()
    pixels = weights_to_pixels(weights, total_width, min_width)
    if not pixels:
        return False
    for col, w in pixels.items():
        tree.column(col, width=w, stretch=False)
    return True


def capture_bill_column_weights(tree, total_width: int | None = None) -> dict | None:
    """抓取当前列像素宽度，归一化为权重；无效时返回 None。

    `total_width` 用于测试；None 时用 `tree.winfo_width()`。
    """
    if total_width is None:
        tree.update_idletasks()
        total_width = tree.winfo_width()
    if total_width < 1:
        return None
    pixels = {c: tree.column(c, "width") for c in BILLS_COLUMNS}
    return pixels_to_weights(pixels, total_width)


# ── 通用列宽工具（适用于任意 ttk.Treeview，不限于账单）──────────────────

def capture_column_weights(tree, columns: tuple[str, ...],
                           total_width: int | None = None) -> dict | None:
    """通用版：抓取任意 ttk.Treeview 指定列的像素宽度，归一化为权重。

    `total_width` 用于测试；None 时用 `tree.winfo_width()`。
    """
    if total_width is None:
        tree.update_idletasks()
        total_width = tree.winfo_width()
    if total_width < 1 or not columns:
        return None
    pixels = {c: tree.column(c, "width") for c in columns}
    return pixels_to_weights(pixels, total_width)


def bind_tree_column_resize(tree, columns: tuple[str, ...],
                            on_resize) -> None:
    """绑定 ttk.Treeview 的列宽拖拽检测。

    ttk.Treeview 自带列宽拖拽（Sizegrip 在 heading 边界），但没有"松手时
    自动通知"的事件。本函数用 `<ButtonPress-1>` + `<ButtonRelease-1>` 配合
    宽度 diff 检测：松手时若任何列宽变化，就抓取新宽度归一化为权重，回调
    `on_resize(weights)`。点击行/heading 非边界不会改宽度，自然过滤。

    使用方式：
        bind_tree_column_resize(
            self._worker_tree,
            ("名称", "单价", "单位", "计费类型"),
            self._on_worker_column_resize,
        )

    约束：
    - `tree.column(c, 'width')` 必须能反映当前像素宽度（stretch=False）
    - 回调在主线程、UI 事件循环里同步执行，不要做耗时操作
    """
    state: dict = {"before": None}

    def _on_press(event):
        tree.update_idletasks()
        state["before"] = {c: tree.column(c, "width") for c in columns}

    def _on_release(event):
        if state["before"] is None:
            return
        tree.update_idletasks()
        after = {c: tree.column(c, "width") for c in columns}
        before = state["before"]
        state["before"] = None
        # 没有任何列宽变化 → 不是列宽拖拽（行点击、heading 点击等）
        if after == before:
            return
        weights = capture_column_weights(tree, columns)
        if weights is not None:
            on_resize(weights)

    tree.bind("<ButtonPress-1>", _on_press, add="+")
    tree.bind("<ButtonRelease-1>", _on_release, add="+")


def resolve_column_weights(project_data: dict, key: str,
                           columns: tuple[str, ...],
                           default_weights: dict) -> dict:
    """通用版：解析指定 key 下的保存列宽权重，支持 fallback。

    优先级：project_data[key]  >  default_weights。**不归一化**。
    列集合为 `columns` 顺序；缺失列从 default_weights 取，default 也缺则跳过。
    """
    saved = (project_data or {}).get(key, {}) or {}
    result: dict[str, float] = {}
    for col in columns:
        w = _safe_positive_float(saved.get(col))
        if w is not None:
            result[col] = w
            continue
        w = _safe_positive_float(default_weights.get(col))
        if w is not None:
            result[col] = w
    return result


def _format_project_date(p: dict) -> str:
    """渲染项目级日期。返回空串表示不展示。"""
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


class ContentArea(tk.Frame):
    def __init__(self, parent, on_name_change=None, on_status_change=None):
        super().__init__(parent, bg=APP_BG)
        self.current_uuid = None
        self.project_data = None
        self.tab_var = tk.StringVar(value="bills")
        self._selected_category = None
        self._edit_cat_id: str = ""
        self._on_name_change = on_name_change
        self._on_status_change = on_status_change
        self._editability: Optional[EditabilityPolicy] = None
        # 列表选中底色（app_config.json: selection_highlight_color）。
        # 账单管理与工种管理的单条数据高亮共用此值。
        self._selection_bg = load_app().get("selection_highlight_color", "#90cdf4")
        self._reviewed_bg = load_app().get("bill_reviewed_row_color", "#e6fffa")
        # 应用内剪贴板：单槽结构，跨项目持久（实例由 ContentArea 持有，切换项目不丢失）
        self._clipboard = AppClipboard()
        self._show_welcome()

    def refresh_app_settings(self) -> None:
        self._selection_bg = load_app().get("selection_highlight_color", "#90cdf4")
        self._reviewed_bg = load_app().get("bill_reviewed_row_color", "#e6fffa")
        if self.current_uuid and self.project_data:
            self._render()

    def set_editability(self, policy: EditabilityPolicy) -> None:
        """由 MainInterface 在创建 ContentArea 后注入的全局可写性策略。"""
        self._editability = policy

    def get_project_status(self) -> Optional[ProjectStatus]:
        """供 EditabilityPolicy.get_current_status 调用，永远返回当前项目状态。"""
        if not self.project_data:
            return None
        return ProjectStatus.from_value(self.project_data.get("status"))

    def _show_welcome(self):
        self.clear()
        frame = tk.Frame(self, bg=APP_BG)
        frame.place(relx=0.5, rely=0.4, anchor="center")
        tk.Label(frame, text="\U0001f44b 欢迎使用", font=FONT_TITLE, bg=APP_BG, fg=TEXT_PRIMARY).pack()
        tk.Label(frame, text="点击左侧【\u2795 新建项目】开始记账", font=FONT_BODY,
                 bg=APP_BG, fg=TEXT_SECONDARY).pack(pady=(12, 0))
        tk.Label(frame, text="或选择一个已有项目查看", font=FONT_BODY,
                 bg=APP_BG, fg=TEXT_SECONDARY).pack(pady=(6, 0))

    def clear(self):
        for w in self.winfo_children():
            w.destroy()

    def load_project(self, uuid):
        if uuid is None:
            self.current_uuid = None
            self.project_data = None
            self._show_welcome()
            return
        self.current_uuid = uuid
        self.project_data = get_project(uuid)
        if not self.project_data:
            messagebox.showerror("错误", "无法加载项目")
            self._show_welcome()
            return
        self._render()

    def _render(self):
        self.clear()
        p = self.project_data

        top = tk.Frame(self, bg=APP_BG, padx=24)
        top.pack(fill=tk.X, pady=(16, 8))

        # 项目名：羽毛笔图标 + 可编辑输入框
        name_container = tk.Frame(top, bg=APP_BG)
        name_container.pack(side=tk.LEFT)
        tk.Label(name_container, text="\U0001f589\ufe0f", font=FONT_HEADING,
                 bg=APP_BG, fg=TEXT_SECONDARY).pack(side=tk.LEFT, padx=(0, 6))
        name_var = tk.StringVar(value=p.get("name", ""))
        self._name_entry = ttk.Entry(name_container, textvariable=name_var, font=FONT_HEADING, width=30)
        self._name_entry.pack(side=tk.LEFT)
        name_var.trace_add("write", lambda *_: self._save_name(name_var.get()))
        if self._editability is not None:
            self._editability.manage(self._name_entry, normally_enabled=True)
        elif not self._editable:
            _set_btn_state(self._name_entry, True)

        # 状态切换（可点击标签）：始终从 self.project_data 读取最新状态
        current_status = ProjectStatus.from_value(self.project_data.get("status"))
        toggle_fg = current_status.color
        toggle_text = f"  {current_status.icon}  {current_status.display_name}  "
        toggle_lbl = tk.Label(top, text=toggle_text, font=("Microsoft YaHei UI", 14, "bold"),
                              bg=APP_BG, fg=toggle_fg, cursor="hand2", padx=10, pady=4)

        def _do_toggle_status(e=None):
            now = ProjectStatus.from_value(self.project_data.get("status"))
            new_status = (ProjectStatus.DONE if now == ProjectStatus.EDITING
                          else ProjectStatus.EDITING)
            self.project_data["status"] = new_status.value
            update_project(self.current_uuid, self.project_data)
            if self._on_status_change is not None:
                try:
                    self._on_status_change(self.current_uuid, new_status)
                except Exception as ex:
                    logger.warning("通知侧边栏项目状态更新失败: %s", ex)
            self._render()
            if self._editability is not None:
                self._editability.refresh()

        toggle_lbl.bind("<Button-1>", _do_toggle_status)
        toggle_lbl.pack(side=tk.LEFT, padx=(12, 0))

        proj_date_text = _format_project_date(p)
        if proj_date_text:
            tk.Label(top, text=f"项目日期：{proj_date_text}",
                     font=FONT_SMALL, bg=APP_BG, fg=TEXT_SECONDARY).pack(side=tk.LEFT, padx=(12, 0))

        tk.Label(top, text=f"创建：{p.get('created_at', 'N/A')}",
                 font=FONT_SMALL, bg=APP_BG, fg=TEXT_SECONDARY).pack(side=tk.RIGHT)

        sep = tk.Frame(self, bg=BORDER, height=1)
        sep.pack(fill=tk.X, padx=24, pady=4)

        nb = tk.Frame(self, bg=APP_BG, padx=24, pady=4)
        nb.pack(fill=tk.X)
        self._tab_buttons = {}
        for val, txt in [("bills", "\U0001f4b0 账单管理"), ("workers", "\U0001f527 工作类型")]:
            rb = tk.Radiobutton(nb, text=txt, variable=self.tab_var, value=val,
                                command=self._switch_tab, font=FONT_BODY_BOLD,
                                bg=APP_BG, activebackground=APP_BG, indicatoron=0,
                                padx=24, pady=10, relief="flat", bd=0,
                                fg=TEXT_SECONDARY, selectcolor=APP_BG)
            rb.pack(side=tk.LEFT, padx=(0, 6))
            self._tab_buttons[val] = rb

        self.content_frame = tk.Frame(self, bg=APP_BG)
        self.content_frame.pack(fill=tk.BOTH, expand=True, padx=24, pady=(8, 16))

        self._switch_tab()

    def _switch_tab(self):
        for w in self.content_frame.winfo_children():
            w.destroy()
        # Update tab highlight
        for val, btn in self._tab_buttons.items():
            if val == self.tab_var.get():
                btn.config(fg=ACCENT, bg=HIGHLIGHT_BG, relief="solid", bd=1)
            else:
                btn.config(fg=TEXT_SECONDARY, bg=APP_BG, relief="flat", bd=0)
        if self.tab_var.get() == "bills":
            cw = self.content_frame.winfo_width()
            logger.debug("_switch_tab: bills, content_frame width=%s", cw)
            self._render_bills()
        else:
            cw = self.content_frame.winfo_width()
            logger.debug("_switch_tab: workers, content_frame width=%s", cw)
            self._render_workers()

    def _save_name(self, name):
        if not self._editable:
            # 已完成状态：项目名是数据字段，不应被改
            return
        cleaned = name.strip()
        if self.project_data and cleaned:
            self.project_data["name"] = cleaned
            update_project(self.current_uuid, self.project_data)
            if self._on_name_change is not None:
                try:
                    self._on_name_change(self.current_uuid, cleaned)
                except Exception as e:
                    logger.warning("通知侧边栏项目名更新失败: %s", e)

    def _get_edit_cat_name(self) -> str:
        """通过 _edit_cat_id 查出 category_order 中对应的当前名字。"""
        if not self._edit_cat_id or not self.project_data:
            return ""
        for cat in self.project_data.category_order:
            cid = cat.id if hasattr(cat, 'id') else ""
            if cid == self._edit_cat_id:
                return cat.name if hasattr(cat, 'name') else str(cat)
        return ""

    def _save_category_name(self) -> None:
        if not self._editable or not hasattr(self, "_cat_name_var") or not self._edit_cat_id:
            return
        cleaned = self._cat_name_var.get().strip()
        old_name = self._get_edit_cat_name()
        if not cleaned:
            logger.debug("_save_category_name: empty input, reset to %r", old_name)
            self._cat_name_var.set(old_name)
            return
        if cleaned == old_name:
            return
        logger.info("_save_category_name: edit_cat_id=%r %r -> %r", self._edit_cat_id, old_name, cleaned)
        for cat in self.project_data.category_order:
            cid = cat.id if hasattr(cat, 'id') else ""
            if cid == self._edit_cat_id and hasattr(cat, 'name'):
                cat.name = cleaned
                for ti in self.project_data.trade_items:
                    if isinstance(ti, dict):
                        if ti.get("category") == old_name:
                            ti["category"] = cleaned
                    elif hasattr(ti, 'category') and ti.category == old_name:
                        ti.category = cleaned
                if hasattr(self.project_data, '_sync_trade_item_category_ids'):
                    self.project_data._sync_trade_item_category_ids()
                update_project(self.current_uuid, self.project_data)
                self._selected_category = cleaned
                self._refresh_category_highlight()
                logger.info("_save_category_name: done, new selected=%r", cleaned)
                break

    @property
    def _editable(self) -> bool:
        """当前项目是否处于"编辑中"状态（=数据可写）。"""
        if not self.project_data:
            return True
        return ProjectStatus.from_value(
            self.project_data.get("status")
        ).is_editable

    def _is_paste_allowed(self) -> bool:
        """右键菜单中「粘贴」项是否可点。

        项目处于"已完成"状态时 → False（菜单项灰显，点击无效）。
        """
        if self._editability is not None:
            return self._editability.is_editable
        return self._editable

    def _confirm_delete(self, title: str, message: str) -> bool:
        from .widgets.confirm_dialog import confirm_dialog
        return confirm_dialog(self.winfo_toplevel(), title, message)

    def _calc_total(self):
        """实时重算合计：每条账单按当前 trade item 单价 + 公式重算。"""
        if not self.project_data:
            return 0.0
        op_map = load_app().get("symbol_mapping", {})
        trade_items = self.project_data.get("trade_items", [])
        bills = self.project_data.get("bills", [])
        total = 0.0
        for b in bills:
            t = recompute_bill_total(b, trade_items, op_map)
            if isinstance(t, (int, float)):
                total += t
        return total

    def _render_bills(self):
        parent = self.content_frame
        for w in parent.winfo_children():
            w.destroy()
        p = self.project_data
        bills = p.get("bills", [])
        logger.debug("_render_bills: content_frame width=%s", parent.winfo_width())
        op_map = load_app().get("symbol_mapping", {})
        trade_items = p.get("trade_items", [])

        header = tk.Frame(parent, bg=APP_BG)
        header.pack(fill=tk.X, pady=(0, 8))

        total = self._calc_total()
        err_cnt = sum(
            1 for b in bills
            if recompute_bill_total(b, trade_items, op_map) == 0
            and b.get("content", "")
        )
        # "合计"红色 + 显示账单条数 + 错误条数
        total_text = f"合计（{len(bills)} 条）：￥{total:.2f}"
        if err_cnt:
            total_text += f"（{err_cnt} 条计算错误）"
        tk.Label(header, text=total_text, font=FONT_HEADING, bg=APP_BG,
                 fg="#c0392b").pack(side=tk.LEFT)

        btn_frame = tk.Frame(header, bg=APP_BG)
        btn_frame.pack(side=tk.RIGHT)
        add_btn = _make_btn(btn_frame, "\u2795 添加记录", self._add_bill, "primary")
        add_btn.pack(side=tk.LEFT, padx=4)
        img_btn = _make_btn(btn_frame, "\U0001f4be 保存为图片", self._export_image, "secondary")
        img_btn.pack(side=tk.LEFT, padx=4)
        # add_btn 受 editability 策略管理；img_btn 在 DONE 状态仍可点（导出图片允许）
        if self._editability is not None:
            self._editability.manage(add_btn, normally_enabled=True)
        elif not self._editable:
            _set_btn_state(add_btn, True)

        # ── 自定义列表（替代 ttk.Treeview，支持公式换行 + 不等行高 + 行内 3 按钮）──
        self._bill_weights = resolve_bill_column_weights(p)
        from .widgets import BillListView
        self._bill_list = BillListView(
            parent,
            bills=bills,
            op_map=op_map,
            trade_items=self.project_data.get("trade_items", []),
            on_edit=self._edit_bill,
            on_move_up=self._move_bill_up,
            on_move_down=self._move_bill_down,
            on_delete=self._delete_bill,
            on_reorder=self._reorder_bill,
            on_top_index_change=self._save_bills_top_index,
            on_column_resize=self._on_bill_column_resize,
            on_copy=self._copy_bill_at,
            on_paste=self._paste_bill_at,
            on_review_toggle=self._set_bill_reviewed,
            on_review_header_toggle=self._toggle_all_bills_reviewed,
            paste_enabled=self._clipboard.has_bill,
            paste_allowed=self._is_paste_allowed,
            weights=self._bill_weights,
            bg=APP_BG,
            editable=self._editable,
            selection_bg=self._selection_bg,
            reviewed_bg=self._reviewed_bg,
        )
        self._bill_list.pack(fill=tk.BOTH, expand=True)
        self._restore_bills_scroll()

        _tc_cfg = load_app().get("tooltips", {})
        hint = TooltipCarousel(
            parent,
            messages=_tc_cfg.get("messages", ["双击行可编辑；拖表头竖条可调列宽"]),
            dwell_per_char_ms=_tc_cfg.get("dwell_per_char_ms", 80),
            font_size=_tc_cfg.get("font_size", 13),
            anchor="e",
        )
        hint.pack(side=tk.BOTTOM, anchor="e", pady=(8, 0))

    def _on_bill_column_resize(self, weights: dict) -> None:
        """用户拖完列分隔条 → 立即更新内存 + 写回项目文件。

        on_column_resize 只在松手时触发一次（motion 不触发），不需要防抖。
        防抖反而会让用户在 300ms 内切换 tab / 重新渲染时被旧值覆盖。
        """
        self._bill_weights = dict(weights)
        logger.debug("_on_bill_column_resize: weights=%s uuid=%s",
                     weights, self.current_uuid)
        if not self.current_uuid:
            return
        try:
            if self.project_data is not None:
                self.project_data["bill_column_widths"] = dict(weights)
                update_project(self.current_uuid, self.project_data)
                logger.debug("_on_bill_column_resize: saved to project uuid=%s",
                             self.current_uuid)
        except Exception as e:
            logger.warning("保存列宽失败: %s", e)

    def _persist_bill_review_state(self) -> None:
        if self.current_uuid:
            update_project(self.current_uuid, self.project_data)

    def _refresh_bill_review_visuals(self) -> None:
        if self._bill_list is not None:
            self._bill_list.set_bills(self.project_data.get("bills", []))

    def _set_bill_reviewed(self, idx: int, reviewed: bool) -> None:
        bills = self.project_data.get("bills", []) if self.project_data else []
        if idx < 0 or idx >= len(bills):
            return
        set_bill_reviewed(bills[idx], reviewed)
        self._persist_bill_review_state()
        self._refresh_bill_review_visuals()

    def _toggle_all_bills_reviewed(self) -> None:
        bills = self.project_data.get("bills", []) if self.project_data else []
        apply_bulk_review(bills)
        self._persist_bill_review_state()
        self._refresh_bill_review_visuals()

    def _on_worker_column_resize(self, weights: dict) -> None:
        """用户拖完 worker heading 边界 → 立即更新内存 + 写回项目文件。

        与 _on_bill_column_resize 同模式：松手时一次回调，写到 worker_column_widths。
        """
        self._worker_weights = dict(weights)
        logger.debug("_on_worker_column_resize: weights=%s uuid=%s",
                     weights, self.current_uuid)
        if not self.current_uuid:
            return
        try:
            if self.project_data is not None:
                self.project_data["worker_column_widths"] = dict(weights)
                update_project(self.current_uuid, self.project_data)
                logger.debug("_on_worker_column_resize: saved to project uuid=%s",
                             self.current_uuid)
        except Exception as e:
            logger.warning("保存 worker 列宽失败: %s", e)

    def _move_bill_up(self, idx: int):
        if self._editability is not None and not self._editability.is_editable:
            return
        bills = self.project_data.get("bills", [])
        if idx <= 0 or idx >= len(bills):
            return
        bills[idx - 1], bills[idx] = bills[idx], bills[idx - 1]
        update_project(self.current_uuid, self.project_data)
        self._render_bills()

    def _move_bill_down(self, idx: int):
        if self._editability is not None and not self._editability.is_editable:
            return
        bills = self.project_data.get("bills", [])
        if idx < 0 or idx >= len(bills) - 1:
            return
        bills[idx], bills[idx + 1] = bills[idx + 1], bills[idx]
        update_project(self.current_uuid, self.project_data)
        self._render_bills()

    def _reorder_bill(self, from_idx: int, to_idx: int):
        if self._editability is not None and not self._editability.is_editable:
            return
        bills = self.project_data.get("bills", [])
        moved_id = bills[from_idx].get("id") if 0 <= from_idx < len(bills) else None
        new_bills = move_item(bills, from_idx, to_idx)
        if new_bills == bills:
            return
        self._save_current_bills_top()
        self.project_data["bills"] = new_bills
        update_project(self.current_uuid, self.project_data)
        self._render_bills()
        if moved_id and self._bill_list is not None:
            for idx, bill in enumerate(self.project_data.get("bills", [])):
                if bill.get("id") == moved_id:
                    self._bill_list.set_selected_index(idx)
                    break

    def _delete_bill(self, idx: int):
        if self._editability is not None and not self._editability.is_editable:
            return
        bills = self.project_data.get("bills", [])
        if idx < 0 or idx >= len(bills):
            return
        if self._confirm_delete("确认", f"删除第 {idx + 1} 条记录？"):
            self._save_current_bills_top()
            bills.pop(idx)
            update_project(self.current_uuid, self.project_data)
            self._render_bills()

    def _save_bills_top_index(self, anchor) -> None:
        if not self.project_data:
            return
        if not isinstance(anchor, dict) or not anchor.get("item_id"):
            return
        view_state = self.project_data.setdefault("view_state", {})
        lists = view_state.setdefault("lists", {})
        if lists.get("bills") == anchor:
            return
        lists["bills"] = dict(anchor)
        if self.current_uuid:
            update_project(self.current_uuid, self.project_data)

    def _save_current_bills_top(self) -> None:
        bill_list = getattr(self, "_bill_list", None)
        if bill_list is not None:
            self._save_bills_top_index(
                bill_list.get_scroll_anchor(lambda idx, item=None: (item or {}).get("id"))
            )

    def _restore_bills_scroll(self) -> None:
        if not self.project_data or self._bill_list is None:
            return
        view_state = self.project_data.get("view_state") or {}
        anchor = (view_state.get("lists") or {}).get("bills")
        if anchor:
            self._bill_list.restore_scroll_anchor(anchor, lambda idx, item=None: (item or {}).get("id"))
            return
        top_id = view_state.get("bills_top_id")
        offset_ratio = view_state.get("bills_top_offset", 0.0)
        if not top_id:
            return
        for idx, bill in enumerate(self.project_data.get("bills", [])):
            if bill.get("id") == top_id:
                self._bill_list.scroll_to_index(idx, offset_ratio)
                return

    # ── 复制 / 粘贴：账单 ──

    def _copy_bill_at(self, idx: int) -> None:
        """账单行右键 → 复制到剪贴板。"""
        if not self.project_data:
            return
        bills = self.project_data.get("bills", [])
        if idx < 0 or idx >= len(bills):
            return
        bill = bills[idx]
        payload = {
            "content": bill.get("content", ""),
            "trade_item_id": bill.get("trade_item_id", ""),
            "trade_item_name_fallback": self._bill_name_fallback(bill),
        }
        # 可选字段：备注 / 日期 / 孤儿快照
        for k in ("note", "work_date_type", "work_date_start",
                  "work_date_end",
                  "frozen_snapshot", "frozen_total"):
            if bill.get(k) is not None and bill.get(k) != "":
                payload[k] = bill[k]
        self._clipboard.set_bill(payload, source_ref=self.current_uuid or "")
        self._toast(f"已复制账单 #{idx + 1}")

    def _paste_bill_at(self, idx: int | None) -> None:
        """账单行 / 空白处右键 → 粘贴到末尾。

        已完成项目下菜单项已灰显，正常路径走不到这里。
        """
        if not self.project_data:
            return
        if not self._clipboard.has_bill():
            return
        try:
            entry = self._clipboard.get_bill()
        except Exception as e:
            messagebox.showerror("粘贴失败", f"剪贴板数据异常：{e}")
            return
        payload = entry["payload"]
        items = self.project_data.get("trade_items", [])
        new_bill = paste_bill(payload, items)
        bills = self.project_data.setdefault("bills", [])
        bills.append(new_bill)
        update_project(self.current_uuid, self.project_data)
        self._render_bills()
        if new_bill.get("trade_item_id"):
            self._toast(f"已粘贴账单到末尾（新行 #{len(bills)}）")
        else:
            self._toast(f"已粘贴为孤儿账单（目标项目无对应工作项目）")

    def _bill_name_fallback(self, bill: dict) -> str:
        """账单在剪贴板里需要一个「名称兜底」，孤儿账单也能粘。

        优先用 resolve_label 取真名；孤儿 / 缺 trade item → 用 frozen_snapshot.name / 旧 trade_item_name。
        """
        items = self.project_data.get("trade_items", []) if self.project_data else []
        # 优先：实时解析
        from ..billing_resolver import resolve_label
        cat, name = resolve_label(bill, items)
        if name:
            return name
        # 兜底：frozen_snapshot
        snap = bill.get("frozen_snapshot")
        if isinstance(snap, dict) and snap.get("name"):
            return snap["name"]
        # 最后兜底：旧字段
        return bill.get("trade_item_name", "")

    def _render_workers(self):
        parent = self.content_frame
        for w in parent.winfo_children():
            w.destroy()
        p = self.project_data
        cats = _project_category_names(p)

        # 确保选中分类有效
        if self._selected_category not in cats:
            self._selected_category = cats[0] if cats else None

        # ── 主容器：左侧分类 + 右侧表格 ──
        main_pane = ttk.PanedWindow(parent, orient=tk.HORIZONTAL)
        main_pane.pack(fill=tk.BOTH, expand=True)

        # ── 左侧分类面板 ──
        left_frame = tk.Frame(main_pane, bg=APP_BG)
        main_pane.add(left_frame, weight=0)

        # Restore saved category width (ratio of content frame width)
        _cat_ratio = load_user().get("category_list_width_ratio",
                                     load_app().get("category_list_width_ratio", 0.25))
        _cat_w = int(max(self.content_frame.winfo_width(), 300) * _cat_ratio)
        _cat_w = max(180, min(500, _cat_w))

        # Track category width changes via Configure event on left_frame
        _cat_save_after_id = [None]

        def _on_cat_configure(e):
            if e.widget is not left_frame:
                return
            logger.debug("_on_cat_configure: left_frame width=%s", e.width)
            if _cat_save_after_id[0]:
                try:
                    left_frame.after_cancel(_cat_save_after_id[0])
                except tk.TclError:
                    pass
            _cat_save_after_id[0] = left_frame.after(
                500, lambda: self._save_category_width(left_frame.winfo_width())
            )

        left_frame.bind("<Configure>", _on_cat_configure)

        def _set_initial_sash():
            try:
                main_pane.sashpos(0, _cat_w)
            except tk.TclError:
                pass
            self.after_idle(lambda: logger.debug(
                "_render_workers: sash=%s left=%s right=%s pwidth=%s",
                main_pane.sashpos(0),
                left_frame.winfo_width(),
                right_frame.winfo_width(),
                parent.winfo_width(),
            ))
        parent.after_idle(_set_initial_sash)

        left_header = tk.Frame(left_frame, bg=APP_BG, pady=4)
        left_header.pack(fill=tk.X, padx=8)
        tk.Label(left_header, text="分类列表", font=FONT_SUBHEADING,
                 bg=APP_BG, fg=TEXT_PRIMARY).pack(side=tk.LEFT)

        # 分类列表（可滚动）
        cat_list_frame = tk.Frame(left_frame, bg=APP_BG)
        cat_list_frame.pack(fill=tk.BOTH, expand=True, padx=4, pady=(4, 8))

        self._cat_scrollable = ScrollableFrame(cat_list_frame, auto_hide_ms=None, bg=APP_BG)
        self._cat_scrollable.pack(fill=tk.BOTH, expand=True)
        self._cat_items_frame = self._cat_scrollable.inner

        for cat in cats:
            self._add_category_item(cat)

        # 左侧底部按钮
        left_btn_frame = tk.Frame(left_frame, bg=APP_BG, pady=8)
        left_btn_frame.pack(fill=tk.X, padx=8)
        left_btns = [
            _make_btn(left_btn_frame, "\u2795 添加分类", self._add_category, "primary"),
            _make_btn(left_btn_frame, "\U0001f504 恢复默认", self._restore_defaults, "ghost"),
        ]
        for b in left_btns:
            b.pack(fill=tk.X, pady=2)
        if self._editability is not None:
            for b in left_btns:
                self._editability.manage(b, normally_enabled=True)

        # ── 右侧工种表格 ──
        right_frame = tk.Frame(main_pane, bg=APP_BG)
        main_pane.add(right_frame, weight=1)

        right_header = tk.Frame(right_frame, bg=APP_BG, pady=4)
        right_header.pack(fill=tk.X)
        cat_name_container = tk.Frame(right_header, bg=APP_BG)
        cat_name_container.pack(side=tk.LEFT)
        tk.Label(cat_name_container, text="\U0001f589\ufe0f", font=FONT_SUBHEADING,
                 bg=APP_BG, fg=TEXT_SECONDARY).pack(side=tk.LEFT, padx=(0, 6))
        # 绑定当前选中分类的 UUID，区分用户主动输入 vs 切换分类时的程序性 set()
        self._edit_cat_id = ""
        for cat in p.category_order:
            cn = cat.name if hasattr(cat, 'name') else str(cat)
            if cn == self._selected_category:
                self._edit_cat_id = cat.id if hasattr(cat, 'id') else ""
                break
        self._cat_name_var = tk.StringVar(value=self._selected_category or "")
        self._cat_name_entry = ttk.Entry(cat_name_container, textvariable=self._cat_name_var,
                                         font=FONT_SUBHEADING, width=30)
        self._cat_name_entry.pack(side=tk.LEFT)
        self._cat_name_var.trace_add("write", lambda *_: self._save_category_name())
        if self._editability is not None:
            self._editability.manage(self._cat_name_entry, normally_enabled=True)
        elif not self._editable:
            _set_btn_state(self._cat_name_entry, True)

        # ── 工种列表（与「账单管理」同款：拖列宽 / 选中行 / ↑↓ 键 / 行内操作）──
        from .widgets import WorkerListView
        self._worker_weights = resolve_worker_column_weights(p)
        self._worker_list = WorkerListView(
            right_frame,
            items=self._get_cat_items(),
            on_activate=self._edit_trade_item_at,
            on_move_up=lambda i: self._move_trade_item(i, -1),
            on_move_down=lambda i: self._move_trade_item(i, +1),
            on_delete=self._delete_trade_item,
            on_reorder=self._reorder_trade_item,
            on_top_index_change=self._save_workers_top_index,
            on_column_resize=self._on_worker_column_resize,
            on_copy=self._copy_trade_item_at,
            on_paste=self._paste_trade_item_at,
            paste_enabled=self._clipboard.has_trade_item,
            paste_allowed=self._is_paste_allowed,
            weights=self._worker_weights,
            selection_bg=self._selection_bg,
            editable=self._editable,
            bg=APP_BG,
        )
        self._worker_list.pack(fill=tk.BOTH, expand=True, pady=(4, 8))
        self._restore_workers_scroll()

        # 右侧底部按钮（编辑/删除/删除分类 三个已移除：用户可双击行编辑、行内删、右键分类删）
        right_btn_frame = tk.Frame(right_frame, bg=APP_BG, pady=4)
        right_btn_frame.pack(fill=tk.X)
        add_trade_btn = _make_btn(right_btn_frame, "\u2795 添加工作", self._add_trade_item_for_selected, "primary")
        add_trade_btn.pack(side=tk.LEFT, padx=4)
        if self._editability is not None:
            self._editability.manage(add_trade_btn, normally_enabled=True)
        elif not self._editable:
            _set_btn_state(add_trade_btn, True)
        _tc_cfg = load_app().get("tooltips", {})
        self._worker_hint = TooltipCarousel(
            parent,
            messages=_tc_cfg.get("messages", ["双击行可编辑；拖表头竖条可调列宽"]),
            dwell_per_char_ms=_tc_cfg.get("dwell_per_char_ms", 80),
            font_size=_tc_cfg.get("font_size", 13),
            anchor="e",
        )
        self._worker_hint.pack(side=tk.BOTTOM, anchor="e", pady=(8, 0))

    def _save_category_width(self, width):
        try:
            cfg = load_user()
            content_width = self.content_frame.winfo_width()
            ratio = round(width / max(content_width, 1), 6)
            cfg["category_list_width_ratio"] = ratio
            save_user(cfg)
            logger.debug("_save_category_width: width=%s ratio=%s content_width=%s to user_config",
                         width, ratio, content_width)
        except Exception:
            pass

    def _add_category_item(self, cat_name):
        """左侧分类列表添加一个分类项"""
        is_selected = (cat_name == self._selected_category)
        bg = HIGHLIGHT_BG if is_selected else APP_BG
        fg = ACCENT if is_selected else TEXT_PRIMARY

        item = tk.Frame(self._cat_items_frame, bg=bg, cursor="hand2", padx=10, pady=8)
        item.pack(fill=tk.X, padx=4, pady=1)

        indicator = None
        if is_selected:
            indicator = tk.Frame(item, bg=ACCENT, width=4)
            indicator.pack(side=tk.LEFT, padx=(0, 8))

        # 统计该分类下的工种数
        count = sum(1 for ti in self.project_data.get("trade_items", []) if _trade_item_category_name(ti, self.project_data) == cat_name)

        weights = _category_list_weights()
        name_w = weights["name"]
        count_w = weights["count"]

        content = tk.Frame(item, bg=bg)
        content.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        content.grid_columnconfigure(0, weight=name_w)
        content.grid_columnconfigure(1, weight=count_w)

        name_lbl = tk.Label(content, text=cat_name, font=FONT_BODY_BOLD, bg=bg, fg=fg,
                            anchor="w", wraplength=0)
        name_lbl.grid(row=0, column=0, sticky="nsew", padx=(0, 4))

        count_lbl = tk.Label(content, text=f"{count}项", font=FONT_SMALL, bg=bg, fg=TEXT_SECONDARY,
                             anchor="e")
        count_lbl.grid(row=0, column=1, sticky="nsew")

        def _update_wraplength(evt=None):
            cw = content.winfo_width()
            if cw > 0:
                nw = int(cw * name_w / (name_w + count_w))
                cw2 = int(cw * count_w / (name_w + count_w))
                try:
                    name_lbl.config(wraplength=max(60, nw - 8))
                    count_lbl.config(wraplength=max(60, cw2 - 8))
                except tk.TclError:
                    pass

        content.bind("<Configure>", _update_wraplength)

        def on_click(e, c=cat_name):
            logger.debug("category_on_click: %r (previous selected=%r)", c, self._selected_category)
            self._selected_category = c
            self._refresh_category_highlight()
            self._refresh_worker_tree()

        def on_right_click(e, c=cat_name):
            self._show_category_context_menu(e, c)

        bind_widgets = [item, content, name_lbl, count_lbl]
        if indicator is not None:
            bind_widgets.append(indicator)
        for w in bind_widgets:
            w.bind("<Button-1>", on_click)
            w.bind("<Button-3>", on_right_click)
            if not is_selected:
                w.bind("<Enter>", lambda e, i=item: i.config(bg="#edf2f7"))
                w.bind("<Leave>", lambda e, i=item: i.config(bg=APP_BG))

    def _refresh_category_highlight(self):
        """刷新左侧分类列表的高亮状态"""
        for w in self._cat_items_frame.winfo_children():
            w.destroy()
        p = self.project_data
        cats = _project_category_names(p)
        if self._selected_category not in cats:
            self._selected_category = cats[0] if cats else None
        for cat in cats:
            self._add_category_item(cat)

    def _get_cat_items(self) -> list[dict]:
        """返回当前选中分类下的工种列表（直接引用 trade_items 里的 dict）。"""
        if not self._selected_category or not self.project_data:
            return []
        return [ti for ti in self.project_data.get("trade_items", [])
                if _trade_item_category_name(ti, self.project_data) == self._selected_category]

    def _get_cat_indices(self) -> list[int]:
        """当前分类下每个工种在 trade_items 全局列表里的位置。"""
        if not self._selected_category or not self.project_data:
            return []
        return [i for i, ti in enumerate(self.project_data.get("trade_items", []))
                if _trade_item_category_name(ti, self.project_data) == self._selected_category]

    def _refresh_worker_tree(self):
        """刷新右侧工种表格（仅更新列表内容，不重建整个面板）。"""
        if not hasattr(self, "_worker_list") or self._worker_list is None:
            return
        if hasattr(self, "_cat_name_var"):
            # 先更新 UUID，再设 var → trace 回调按新 UUID 查找，新旧名一致→直接 return
            self._edit_cat_id = ""
            if self.project_data and self._selected_category:
                for cat in self.project_data.category_order:
                    cn = cat.name if hasattr(cat, 'name') else str(cat)
                    if cn == self._selected_category:
                        self._edit_cat_id = cat.id if hasattr(cat, 'id') else ""
                        break
            logger.debug("_refresh_worker_tree: edit_cat_id=%r set cat_name_var to %r",
                         self._edit_cat_id, self._selected_category or "请选择分类")
            self._cat_name_var.set(self._selected_category or "请选择分类")
        self._worker_list.set_items(self._get_cat_items())

    def _add_bill(self):
        if not self.project_data:
            return
        if self._editability is not None and not self._editability.is_editable:
            return
        self._save_current_bills_top()
        EditBillDialog(self, self.project_data, self._refresh_view,
                       editable=self._editable)

    def _edit_bill(self, idx):
        if not self.project_data:
            return
        if self._editability is not None and not self._editability.is_editable:
            return
        self._save_current_bills_top()
        bill = self.project_data["bills"][idx]
        EditBillDialog(self, self.project_data, self._refresh_view, bill,
                       editable=self._editable)

    def _export_image(self):
        p = self.project_data
        if not p:
            return
        bills = p.get("bills", [])
        if not bills:
            messagebox.showinfo("提示", "暂无记录可导出")
            return

        user_cfg = load_user()
        op_map = load_app().get("symbol_mapping", {})

        # 生成图片前检测孤儿账单 → 阻止导出
        trade_items = p.get("trade_items", [])
        bills = p.get("bills", [])
        orphans = orphan_bills(bills, trade_items)
        if orphans:
            messagebox.showwarning(
                "存在孤儿账单",
                f"当前项目有 {len(orphans)} 条账单引用的工作项目已被删除或重命名。\n"
                "请先处理孤儿账单后再导出图片。",
                parent=self,
            )
            return

        path = filedialog.asksaveasfilename(
            defaultextension=".png",
            filetypes=[("PNG图片", "*.png"), ("所有文件", "*.*")],
            title="保存图片",
            initialfile=f"{p.get('name', '账单')}.png"
        )
        if not path:
            return

        ec = ExportDefaults.from_dict(user_cfg.get("export_defaults", {}))

        blocks, _total = build_export_blocks(p, op_map, ec)

        try:
            import sys
            font_path = None
            if sys.platform == "win32":
                sr = os.environ.get("SystemRoot", "")
                if sr:
                    c = os.path.join(sr, "Fonts", "msyh.ttc")
                    if os.path.isfile(c):
                        font_path = c
            elif sys.platform == "linux":
                for fp in ("/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc",
                           "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc"):
                    if os.path.isfile(fp):
                        font_path = fp
                        break

            save_styled_image(blocks, path, font_path=font_path,
                              bg_color=ec.bg_color,
                              text_color=ec.text_colors.normal)

            if sys.platform == "win32":
                display_path = os.path.normpath(path)
            else:
                display_path = path

            self._show_success_dialog(display_path)
        except Exception as e:
            logger.error("导出图片失败: %s", e)
            messagebox.showerror("错误", f"导出失败：{e}")

    def _show_success_dialog(self, path: str) -> None:
        dialog = tk.Toplevel(self)
        dialog.title("成功")
        dialog.resizable(False, False)
        dialog.transient(self)
        dialog.grab_set()
        dialog.configure(bg=APP_BG)

        w, h = 520, 160
        x = self.winfo_rootx() + (self.winfo_width() - w) // 2
        y = self.winfo_rooty() + (self.winfo_height() - h) // 2
        dialog.geometry(f"{w}x{h}+{x}+{y}")

        tk.Label(dialog, text="图片已保存到：", font=FONT_BODY,
                 bg=APP_BG, fg=TEXT_PRIMARY).pack(pady=(16, 4), padx=16, anchor="w")
        entry = ttk.Entry(dialog, font=FONT_SMALL, width=60)
        entry.insert(0, path)
        entry.config(state="readonly")
        entry.pack(fill=tk.X, padx=16)
        entry.focus_set()
        entry.selection_range(0, tk.END)

        btn_frame = tk.Frame(dialog, bg=APP_BG)
        btn_frame.pack(pady=(16, 0))
        _make_btn(btn_frame, "确定", dialog.destroy, "primary").pack(side=tk.LEFT, padx=4)

    def _add_category(self):
        if self._editability is not None and not self._editability.is_editable:
            return
        dialog = tk.Toplevel(self)
        dialog.title("添加工作类型")
        dialog.resizable(False, False)
        dialog.transient(self)
        dialog.grab_set()
        dialog.configure(bg=APP_BG)

        w, h = 500, 180
        x = self.winfo_rootx() + (self.winfo_width() - w) // 2
        y = self.winfo_rooty() + (self.winfo_height() - h) // 2
        dialog.geometry(f"{w}x{h}+{x}+{y}")

        tk.Label(dialog, text="工作类型名称：", font=FONT_BODY, bg=APP_BG).pack(pady=(20, 4), padx=20, anchor="w")
        entry, var = _input_entry(dialog, placeholder="如：泥瓦工程")
        entry.pack(fill=tk.X, padx=20)
        entry.focus_set()

        btn_frame = tk.Frame(dialog, bg=APP_BG)
        btn_frame.pack(pady=(16, 0))
        _make_btn(btn_frame, "取消", dialog.destroy, "ghost").pack(side=tk.LEFT, padx=4)
        _make_btn(btn_frame, "确定", lambda: self._confirm_add_cat(dialog, var.get()), "primary").pack(side=tk.LEFT, padx=4)

    def _confirm_add_cat(self, dialog, name):
        name = name.strip()
        if not name:
            messagebox.showwarning("提示", "请输入名称")
            return
        co = self.project_data.setdefault("category_order", [])
        if name not in co:
            co.append(name)
            self.project_data["category_order"] = co
        update_project(self.current_uuid, self.project_data)
        dialog.destroy()
        self._selected_category = name
        self._render()

    def _add_trade_item_for_selected(self):
        if not self._selected_category:
            messagebox.showwarning("提示", "请先选择一个分类")
            return
        self._add_trade_item(self._selected_category)

    def _add_trade_item(self, category):
        if self._editability is not None and not self._editability.is_editable:
            return
        self._save_current_workers_top()
        cats = _project_category_names(self.project_data)

        units = sorted(set(read_billing(ti).unit for ti in self.project_data.get("trade_items", [])))
        items = self.project_data.get("trade_items", [])
        next_seq = max((ti.get("seq", 0) for ti in items), default=0) + 1
        dummy = {"seq": next_seq, "category": category, "name": "", "unit": units[0] if units else ""}
        EditTradeItemDialog(self, dummy, cats, units, self.project_data, self.current_uuid,
                            self._refresh_workers_only, editable=self._editable)

    def _edit_trade_item(self, item):
        if self._editability is not None and not self._editability.is_editable:
            return
        self._save_current_workers_top()
        cats = _project_category_names(self.project_data)

        units = sorted(set(read_billing(ti).unit for ti in self.project_data.get("trade_items", [])))
        EditTradeItemDialog(self, item, cats, units, self.project_data, self.current_uuid,
                            self._refresh_workers_only, editable=self._editable)

    def _edit_trade_item_at(self, idx: int) -> None:
        """行内 / 双击触发的编辑：按当前分类内 idx 找到对应 trade_item。"""
        if self._editability is not None and not self._editability.is_editable:
            return
        cat_indices = self._get_cat_indices()
        if idx < 0 or idx >= len(cat_indices):
            return
        items = self.project_data.get("trade_items", [])
        self._edit_trade_item(items[cat_indices[idx]])

    def _delete_trade_item(self, idx: int) -> None:
        """行内删除按钮触发的删除（软删除流程：影响到的账单转孤儿）。"""
        if self._editability is not None and not self._editability.is_editable:
            return
        cat_indices = self._get_cat_indices()
        if idx < 0 or idx >= len(cat_indices):
            return
        items = self.project_data.get("trade_items", [])
        item = items[cat_indices[idx]]

        # 找出所有引用此 trade item 的账单
        tid = item.get("id", "")
        affected_bills = [
            b for b in self.project_data.get("bills", [])
            if b.get("trade_item_id") == tid
        ]
        warn_msg = f"删除「{item['name']}」？"
        if affected_bills:
            warn_msg += (
                f"\n\n有 {len(affected_bills)} 条账单引用此工作项目。"
                "删除后这些账单将显示为「已删除」并保留最后已知金额（不再随单价变化）。"
            )
        if not self._confirm_delete("确认", warn_msg):
            return
        self._save_current_workers_top()

        # 软删除：先冻结账单的当前状态
        ti_billing = read_billing(item)
        op_map = load_app().get("symbol_mapping", {})
        for b in affected_bills:
            b["frozen_snapshot"] = {
                "name": item.get("name", ""),
                "category": item.get("category", ""),
                "has_unit": ti_billing.has_unit,
                "unit_price": ti_billing.unit_price,
                "unit": ti_billing.unit,
            }
            b["frozen_total"] = recompute_bill_total(
                {**b.to_dict(), "trade_item_id": tid} if hasattr(b, "to_dict") else {**b, "trade_item_id": tid},
                items,
                op_map,
            )
            b["trade_item_id"] = ""
            b["_needs_attention"] = True

        del items[cat_indices[idx]]
        update_project(self.current_uuid, self.project_data)
        # 刷新 workers 和 bills（bills 列表里受影响行变红）
        self._refresh_workers_only()
        if self._bill_list is not None:
            self._bill_list.set_bills(self.project_data.get("bills", []))

    def _move_trade_item(self, idx: int, direction: int) -> None:
        """行内上移/下移：direction=-1 上移，+1 下移。在当前分类内交换相邻项。"""
        if self._editability is not None and not self._editability.is_editable:
            return
        cat_indices = self._get_cat_indices()
        if idx < 0 or idx >= len(cat_indices):
            return
        target = idx + direction
        if target < 0 or target >= len(cat_indices):
            return  # 已到分类内边界
        items = self.project_data.get("trade_items", [])
        pos_a = cat_indices[idx]
        pos_b = cat_indices[target]
        items[pos_a], items[pos_b] = items[pos_b], items[pos_a]
        update_project(self.current_uuid, self.project_data)
        # 选区跟随：移到新位置后仍选中同一项
        self._refresh_workers_only()
        self._worker_list.set_selected_index(target)

    def _reorder_trade_item(self, from_idx: int, to_idx: int) -> None:
        if self._editability is not None and not self._editability.is_editable:
            return
        cat_items = self._get_cat_items()
        moved_id = cat_items[from_idx].get("id") if 0 <= from_idx < len(cat_items) else None
        visible_ids = [item.get("id", "") for item in cat_items]
        items = self.project_data.get("trade_items", [])
        new_items = reorder_subset_by_ids(
            items, visible_ids, from_idx, to_idx,
            id_getter=lambda item: item.get("id", ""),
        )
        if new_items == items:
            return
        self._save_current_workers_top()
        self.project_data["trade_items"] = new_items
        update_project(self.current_uuid, self.project_data)
        self._refresh_workers_only()
        if moved_id and self._worker_list is not None:
            for idx, item in enumerate(self._get_cat_items()):
                if item.get("id") == moved_id:
                    self._worker_list.set_selected_index(idx)
                    break

    def _category_scroll_key(self) -> str:
        return str(self._selected_category or "")

    def _worker_list_scroll_key(self) -> str:
        return f"workers:{self._category_scroll_key()}"

    def _save_workers_top_index(self, anchor) -> None:
        if not self.project_data:
            return
        if not isinstance(anchor, dict) or not anchor.get("item_id"):
            return
        view_state = self.project_data.setdefault("view_state", {})
        lists = view_state.setdefault("lists", {})
        key = self._worker_list_scroll_key()
        if lists.get(key) == anchor:
            return
        lists[key] = dict(anchor)
        if self.current_uuid:
            update_project(self.current_uuid, self.project_data)

    def _save_current_workers_top(self) -> None:
        worker_list = getattr(self, "_worker_list", None)
        if worker_list is not None:
            self._save_workers_top_index(
                worker_list.get_scroll_anchor(lambda idx, item=None: (item or {}).get("id"))
            )

    def _restore_workers_scroll(self) -> None:
        if not self.project_data or self._worker_list is None:
            return
        view_state = self.project_data.get("view_state") or {}
        anchor = (view_state.get("lists") or {}).get(self._worker_list_scroll_key())
        if anchor:
            self._worker_list.restore_scroll_anchor(anchor, lambda idx, item=None: (item or {}).get("id"))
            return
        by_cat = view_state.get("workers_top_id_by_category", {}) or {}
        offsets = view_state.get("workers_top_offset_by_category", {}) or {}
        top_id = by_cat.get(self._category_scroll_key())
        offset_ratio = offsets.get(self._category_scroll_key(), 0.0)
        if not top_id:
            return
        for idx, item in enumerate(self._get_cat_items()):
            if item.get("id") == top_id:
                self._worker_list.scroll_to_index(idx, offset_ratio)
                return

    # ── 复制 / 粘贴：工作类型 ──

    def _copy_trade_item_at(self, idx: int) -> None:
        """工种行右键 → 复制到剪贴板。"""
        if not self.project_data:
            return
        cat_indices = self._get_cat_indices()
        if idx < 0 or idx >= len(cat_indices):
            return
        items = self.project_data.get("trade_items", [])
        ti = items[cat_indices[idx]]
        billing = read_billing(ti)
        payload = {
            "category": ti.get("category", ""),
            "name": ti.get("name", ""),
            "has_unit": billing.has_unit,
            "unit_price": billing.unit_price,
            "unit": billing.unit,
        }
        self._clipboard.set_trade_item(payload, source_ref=self.current_uuid or "")
        self._toast(f"已复制工作「{payload['name']}」")

    def _paste_trade_item_at(self, idx: int | None) -> None:
        """工种行 / 空白处右键 → 粘贴到末尾。

        已完成项目下菜单项已灰显，正常路径走不到这里。
        """
        if not self.project_data:
            return
        if not self._clipboard.has_trade_item():
            return
        try:
            entry = self._clipboard.get_trade_item()
        except Exception as e:
            messagebox.showerror("粘贴失败", f"剪贴板数据异常：{e}")
            return
        payload = entry["payload"]
        items = self.project_data.get("trade_items", [])
        cat_order = self.project_data.get("category_order", [])
        new_ti = paste_trade_item(payload, items, cat_order)
        items.append(new_ti)
        if unique_category_after_paste(new_ti["category"], cat_order):
            cat_order.append(new_ti["category"])
            self.project_data["category_order"] = cat_order
        update_project(self.current_uuid, self.project_data)
        self._render()
        self._toast(f"已粘贴工作「{new_ti['name']}」")

    def _delete_category(self, cat: str) -> None:
        """删除指定分类（右键菜单触发的入口）。所有受影响账单软删除为孤儿。"""
        if self._editability is not None and not self._editability.is_editable:
            return
        items = self.project_data.get("trade_items", [])
        deleting = [ti for ti in items if _trade_item_category_name(ti, self.project_data) == cat]
        deleting_ids = {ti.get("id", "") for ti in deleting}
        affected_bills = [
            b for b in self.project_data.get("bills", [])
            if b.get("trade_item_id") in deleting_ids
        ]
        warn_msg = f"删除分类「{cat}」？"
        if deleting:
            warn_msg = f"删除分类「{cat}」及其所有工种？"
            if affected_bills:
                warn_msg += (
                    f"\n\n有 {len(affected_bills)} 条账单引用此分类下的工作项目，"
                    "删除后将显示为「已删除」并保留最后已知金额（不再随单价变化）。"
                )
        if not self._confirm_delete("确认", warn_msg):
            return

        # 软删除流程：先冻结受影响账单
        if deleting:
            op_map = load_app().get("symbol_mapping", {})
            for ti in deleting:
                tid = ti.get("id", "")
                ti_billing = read_billing(ti)
                for b in self.project_data.get("bills", []):
                    if b.get("trade_item_id") == tid:
                        b["frozen_snapshot"] = {
                            "name": ti.get("name", ""),
                            "category": _trade_item_category_name(ti, self.project_data),
                            "has_unit": ti_billing.has_unit,
                            "unit_price": ti_billing.unit_price,
                            "unit": ti_billing.unit,
                        }
                        b["frozen_total"] = recompute_bill_total(
                            {**b.to_dict(), "trade_item_id": tid} if hasattr(b, "to_dict") else {**b, "trade_item_id": tid},
                            items,
                            op_map,
                        )
                        b["trade_item_id"] = ""
                        b["_needs_attention"] = True

        self.project_data["trade_items"] = [
            ti for ti in items if _trade_item_category_name(ti, self.project_data) != cat
        ]
        co = self.project_data.get("category_order", [])
        self.project_data["category_order"] = [c for c in co if _category_name(c) != cat]
        update_project(self.current_uuid, self.project_data)
        if self._selected_category == cat:
            self._selected_category = None
        self._render()

    def _move_category_up(self, cat: str) -> None:
        """把分类在 category_order 中上移一位。"""
        if self._editability is not None and not self._editability.is_editable:
            return
        cats = self._build_category_list()
        if cat not in cats:
            return
        idx = cats.index(cat)
        if idx <= 0:
            return  # 已经在最上面
        cats[idx - 1], cats[idx] = cats[idx], cats[idx - 1]
        self.project_data["category_order"] = _category_order_for_names(self.project_data, cats)
        update_project(self.current_uuid, self.project_data)
        self._refresh_workers_only()

    def _move_category_down(self, cat: str) -> None:
        """把分类在 category_order 中下移一位。"""
        if self._editability is not None and not self._editability.is_editable:
            return
        cats = self._build_category_list()
        if cat not in cats:
            return
        idx = cats.index(cat)
        if idx >= len(cats) - 1:
            return  # 已经在最下面
        cats[idx + 1], cats[idx] = cats[idx], cats[idx + 1]
        self.project_data["category_order"] = _category_order_for_names(self.project_data, cats)
        update_project(self.current_uuid, self.project_data)
        self._refresh_workers_only()

    def _build_category_list(self) -> list[str]:
        """构造完整的分类列表（cat_order 在前，trade_items 里未列出的追加到末尾）。"""
        return _project_category_names(self.project_data)

    def _show_category_context_menu(self, event, cat: str) -> None:
        """分类列表的右键菜单：上移 / 下移 / 删除分类。已完成状态不提供。"""
        if not self._category_context_menu_allowed(cat):
            return
        cats = self._build_category_list()
        idx = cats.index(cat)
        menu = tk.Menu(self, tearoff=0)
        # 上移：非最顶
        up_state = "normal" if idx > 0 else "disabled"
        menu.add_command(label="\u2b06\ufe0f 上移",
                         command=lambda: self._move_category_up(cat),
                         state=up_state)
        # 下移：非最底
        down_state = "normal" if idx < len(cats) - 1 else "disabled"
        menu.add_command(label="\u2b07\ufe0f 下移",
                         command=lambda: self._move_category_down(cat),
                         state=down_state)
        menu.add_separator()
        menu.add_command(label="\U0001f5d1\ufe0f 删除分类",
                         command=lambda: self._delete_category(cat))
        try:
            menu.tk_popup(event.x_root, event.y_root)
        finally:
            menu.grab_release()

    def _category_context_menu_allowed(self, cat: str) -> bool:
        cats = self._build_category_list()
        if cat not in cats:
            return False
        status = ProjectStatus.from_value((self.project_data or {}).get("status"))
        if status == ProjectStatus.DONE:
            return False
        if self._editability is not None:
            return self._editability.is_editable
        return self._editable

    def _refresh_workers_only(self):
        """仅刷新工作类型页面（不重新渲染整个项目视图）"""
        if self.current_uuid:
            self.project_data = get_project(self.current_uuid)
            if self.tab_var.get() == "workers":
                self._render_workers()
            else:
                self._render()

    def _restore_defaults(self):
        if self._editability is not None and not self._editability.is_editable:
            return
        if not self._confirm_delete("确认", "恢复默认工作类型？当前所有工作类型将被替换。"):
            return
        category_order, defaults = _default_worker_data()
        self.project_data["trade_items"] = defaults
        self.project_data["category_order"] = category_order
        update_project(self.current_uuid, self.project_data)
        self._render()

    def _refresh_view(self):
        if self.current_uuid:
            self.project_data = get_project(self.current_uuid)
            self._render()

    def _toast(self, msg: str, ms: int = 1500) -> None:
        """屏幕底部轻量提示（1.5s 自动消失）。不阻塞用户。"""
        try:
            top = self.winfo_toplevel()
        except Exception:
            return
        try:
            tw = tk.Toplevel(top)
            tw.wm_overrideredirect(True)
            tw.configure(bg="#2d3748")
            lbl = tk.Label(tw, text=msg, bg="#2d3748", fg="white",
                           font=FONT_BODY, padx=14, pady=6)
            lbl.pack()
            # 定位：屏幕底部居中
            top.update_idletasks()
            sx = top.winfo_screenwidth()
            sy = top.winfo_screenheight()
            tw.update_idletasks()
            w = tw.winfo_reqwidth()
            h = tw.winfo_reqheight()
            x = (sx - w) // 2
            y = sy - h - 60
            tw.geometry(f"{w}x{h}+{x}+{y}")
            tw.after(ms, tw.destroy)
        except Exception:
            pass
