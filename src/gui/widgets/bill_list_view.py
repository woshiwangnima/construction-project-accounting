"""账单列表 widget - 复用 ListViewBase，仅提供账单特有的单元格渲染。

设计：所有通用逻辑（header、body、列宽拖拽、行选中、↑/↓ 键、共享操作栏）都在
ListViewBase 里，本类只负责把一条账单数据 → 数据列 Label。

依赖 BILLS_COLUMNS / BILLS_DEFAULT_WEIGHTS / BILLS_MIN_WIDTH 来定义列与默认权重。
"""
import tkinter as tk

from ..theme import (
    APP_BG, ACCENT, REVIEW_BG, ROW_STRIPE, SYSTEM_GREEN, SYSTEM_RED,
    TEXT_PRIMARY,
)
from ..font_manager import font_manager
from .list_view_base import ListViewBase
from ..content import (
    BILLS_MIN_WIDTH,
    _format_formula, _format_bill_date,
)
from ...calculator import to_display
from ...bill_recompute import (
    BillCalculation,
    prepare_bill_calculations,
)
from ...bill_review import is_bill_reviewed
from ..shortcut_manager import shortcut_manager as sm

# 孤儿账单行的文字色（红）+ 前缀图标
ORPHAN_FG = SYSTEM_RED
ORPHAN_PREFIX = "⚠ "
BILL_SECONDARY_FG = "#5f6368"
BILL_TERTIARY_FG = "#6e6e73"

# Keep narrow columns readable while allowing the table to wrap long Chinese
# names, formulas and notes.  The action column remains fixed by the base view.
BILL_COLUMN_MIN_WIDTHS = {
    "#": 40,
    "审核": 44,
    "工作内容": 88,
    "公式": 84,
    "公式结果": 68,
    "单价": 76,
    "金额": 82,
    "备注": 88,
    "日期": 76,
    "修改时间": 96,
    "操作": 52,
}


class BillListView(ListViewBase):
    """账单列表 widget。"""

    def __init__(
        self,
        parent,
        bills,
        op_map,
        trade_items=None,
        on_edit=None,
        on_move_up=None,
        on_move_down=None,
        on_delete=None,
        on_reorder=None,
        on_column_resize=None,
        on_review_toggle=None,
        on_review_header_toggle=None,
        on_sort_by_modified=None,
        columns=None,
        weights=None,
        hidden_cols=None,
        editable: bool = True,
        selection_bg: str = ACCENT,
        reviewed_bg: str = REVIEW_BG,
        mode: str = "complex",
        calculations: list[BillCalculation] | None = None,
        **kwargs,
    ):
        self._op_map = op_map
        self._trade_items = trade_items or []
        self._calculations = list(calculations or [])
        if len(self._calculations) != len(bills or []):
            self._calculations = []
        self._on_edit = on_edit
        self._on_review_toggle = on_review_toggle
        self._reviewed_bg = reviewed_bg
        self._mode = mode
        all_cols = columns or []
        hidden_set = set(hidden_cols or [])

        header_click_map = {}
        if on_review_header_toggle is not None and "审核" in all_cols:
            header_click_map["审核"] = lambda col: on_review_header_toggle()
        if on_sort_by_modified is not None and "修改时间" in all_cols:
            header_click_map["修改时间"] = lambda col: on_sort_by_modified()

        super().__init__(
            parent,
            columns=all_cols,
            default_weights=weights or {},
            min_width=BILLS_MIN_WIDTH,
            action_col="操作",
            action_col_width=52,
            on_column_resize=on_column_resize,
            on_move_up=on_move_up,
            on_move_down=on_move_down,
            on_delete=on_delete,
            on_reorder=on_reorder,
            scroll_id_getter=lambda idx, item=None: (item or {}).get("id"),
            on_row_activated=on_edit,
            selection_bg=selection_bg,
            row_bg_getter=self._row_bg_for_bill,
            editable=editable,
            wrap_cols=("工作内容", "公式", "备注", "修改时间"),
            header_click_map=header_click_map,
            header_labels={"操作": "排序"},
            hidden_cols=hidden_set,
            action_delete=True,
            shared_actions=True,
            initial_items=list(bills or []),
            column_min_widths=BILL_COLUMN_MIN_WIDTHS,
            **kwargs,
        )

    def _ensure_calculations(self) -> None:
        if len(self._calculations) != len(self._items):
            self._calculations = prepare_bill_calculations(
                self._items, self._trade_items, self._op_map
            )

    def _row_bg_for_bill(self, idx: int, bill: dict) -> str:
        if is_bill_reviewed(bill):
            return self._reviewed_bg
        return ROW_STRIPE if idx % 2 == 1 else "white"

    def _review_command(self, idx: int):
        """Build a command that reads the current review state on click."""
        return (
            lambda i=idx: self._on_review_toggle
            and self._on_review_toggle(i, not is_bill_reviewed(self._items[i]))
        )

    def set_trade_items(self, trade_items):
        """Trade item 列表变更后调用，重新渲染。"""
        self.update_data(self._items, trade_items=trade_items)

    def set_bills(self, bills):
        """账单列表变更后调用，重新渲染。"""
        self.update_data(bills)

    def update_data(self, bills, trade_items=None, calculations=None) -> None:
        """Update the data source while keeping the list widget alive.

        ContentArea uses this method for ordinary edits and refreshes.  The
        list still rebuilds its rows for now, but its toolbar, canvas, header,
        bindings and parent layout remain stable until list virtualization is
        introduced.
        """
        self._items = list(bills or [])
        if trade_items is not None:
            self._trade_items = trade_items or []
        if calculations is None:
            self._calculations = prepare_bill_calculations(
                self._items, self._trade_items, self._op_map
            )
        else:
            self._calculations = list(calculations)
            if len(self._calculations) != len(self._items):
                self._calculations = prepare_bill_calculations(
                    self._items, self._trade_items, self._op_map
                )
        if self._selected_idx is not None and self._selected_idx >= len(self._items):
            self._selected_idx = None
        self._update_action_toolbar()
        self.refresh_items(self._items)

    def set_items(self, items: list) -> None:
        """Keep the base API while rebuilding the one-pass calculation cache."""
        self.set_bills(items)

    def update_review_visuals(self) -> None:
        """Update review buttons/backgrounds without rebuilding every row."""
        for idx, bill in enumerate(self._items):
            widgets = self._get_row_widgets(idx)
            if widgets is None:
                continue
            review_button = widgets.get("审核")
            if review_button is not None:
                review_button.config(
                    text="☑" if is_bill_reviewed(bill) else "☐",
                    fg=SYSTEM_GREEN if is_bill_reviewed(bill) else BILL_TERTIARY_FG,
                    command=self._review_command(idx) if self._editable else None,
                )
            self._apply_row_bg(idx)

    def set_mode(
        self,
        mode: str,
        columns: list[str],
        weights: dict,
        hidden_cols: list[str],
        *,
        refresh: bool = True,
    ) -> None:
        self._mode = mode
        self._columns = tuple(columns)
        self._data_cols = tuple(c for c in self._columns if c != self._action_col)
        self._weights = dict(weights)
        self._hidden_cols = set(hidden_cols)
        if refresh:
            self._render_rows()

    def _on_row_right_click(self, event, idx) -> None:
        """账单行 / 空白处右键：弹「复制 / 粘贴」菜单。"""
        if event is None:
            return  # 事件对象缺失，无法定位菜单
        menu = self._build_row_right_click_menu(idx)
        if menu is None:
            return  # 没菜单项就不弹
        try:
            menu.tk_popup(event.x_root, event.y_root)
        finally:
            menu.grab_release()

    def _build_row_right_click_menu(self, idx):
        """构造右键菜单（与 _on_row_right_click 分离，方便测试断言）。返回 None 表示无可弹项。"""
        menu = tk.Menu(self, tearoff=0)
        has_items = False
        # 复制
        if idx is not None and self._on_copy:
            menu.add_command(
                label="\U0001f4cb\ufe0f 复制",
                command=lambda i=idx: self._on_copy(i),
                accelerator=sm.get_accel("copy"),
            )
            has_items = True
        # 分隔线
        if has_items:
            menu.add_separator()
        # 粘贴
        paste_enabled = self._paste_enabled is None or self._paste_enabled()
        paste_allowed = self._paste_allowed is None or self._paste_allowed()
        if self._on_paste and paste_enabled:
            menu.add_command(
                label="\U0001f4dd\ufe0f 粘贴",
                command=lambda i=idx: self._on_paste(i),
                state="normal" if paste_allowed else "disabled",
                accelerator=sm.get_accel("paste"),
            )
            has_items = True
            menu.add_separator()
        # 删除
        del_allowed = self._editable
        if idx is not None and self._on_delete:
            menu.add_command(
                label="\U0001f5d1\ufe0f 删除",
                command=lambda i=idx: self._on_delete(i),
                state="normal" if del_allowed else "disabled",
                accelerator=sm.get_accel("delete_item"),
            )
            has_items = True
        if self._add_reorder_menu_items(menu, idx):
            if has_items:
                menu.add_separator()
            has_items = True
        if not has_items:
            return None
        return menu

    def _create_row_widgets(self, row_frame, idx, b) -> dict:
        """填一行：7 个数据列 Label（操作列由基类自动加 RowActionButtons）。"""
        self._ensure_calculations()
        calc = self._calculations[idx]
        content = b.get("content", "")
        note = b.get("note", "")
        date = _format_bill_date(b)

        # All resolver/calculator work is shared by the summary and this row.
        cat, name = calc.category, calc.name
        orphan = calc.orphan
        billing = calc.billing
        total_val = calc.total

        formula_result_str = ""
        if calc.formula_value is not None:
            formula_result_str = f"{calc.formula_value:.10f}".rstrip("0").rstrip(".") or "0"

        if calc.canonical:
            # The list historically shows the entered quantity formula as-is;
            # the extra outer layer is only used by image export.
            formula_display = to_display(calc.canonical)
        else:
            formula_display = _format_formula(content, self._op_map)

        if billing.is_per_unit:
            qty_str = formula_display
            price_str = billing.format_price()
        else:
            qty_str = "-"
            price_str = "无单价"

        if isinstance(total_val, (int, float)):
            total_str = f"￥{total_val:.2f}"
            total_color = ORPHAN_FG if orphan else TEXT_PRIMARY
        else:
            total_str = "错误" if content else ""
            total_color = BILL_TERTIARY_FG

        # 名称带 ⚠ 前缀（孤儿）或 类别 - 名称
        display_name = f"{ORPHAN_PREFIX}{name}" if orphan else name
        if cat and not orphan:
            display_name = f"{cat} - {name}"
        # 孤儿时也加上类别（来自 frozen_snapshot）
        if orphan and cat:
            display_name = f"{ORPHAN_PREFIX}{cat} - {name}（已删除）"
        cells: dict = {
            "#": tk.Label(row_frame, text=str(idx + 1), font=font_manager.get("body"), anchor="center", padx=4),
            "审核": tk.Button(
                row_frame,
                text="☑" if is_bill_reviewed(b) else "☐",
                font=font_manager.get("body_bold"),
                relief="flat",
                bd=0,
                fg=SYSTEM_GREEN if is_bill_reviewed(b) else BILL_TERTIARY_FG,
                cursor="hand2" if self._editable else "arrow",
                command=self._review_command(idx) if self._editable else None,
            ),
            "工作内容": tk.Label(row_frame, text=display_name, font=font_manager.get("body"), anchor="w", padx=6,
                                 wraplength=0, justify="left",
                                 fg=ORPHAN_FG if orphan else TEXT_PRIMARY),
            "公式": tk.Label(row_frame, text=qty_str, font=font_manager.get("body"), anchor="w", padx=6,
                             wraplength=0, justify="left", fg=BILL_SECONDARY_FG),
            "公式结果": tk.Label(row_frame, text=formula_result_str, font=font_manager.get("body"), anchor="e", padx=6,
                                fg=BILL_SECONDARY_FG),
            "单价": tk.Label(row_frame, text=price_str, font=font_manager.get("body"), anchor="w", padx=6,
                              fg=ORPHAN_FG if orphan else TEXT_PRIMARY),
            "金额": tk.Label(row_frame, text=total_str, font=font_manager.get("body_bold"), anchor="e", padx=6,
                             fg=total_color),
            "备注": tk.Label(row_frame, text=note, font=font_manager.get("body"), anchor="w", padx=6,
                             wraplength=0, justify="left", fg=BILL_SECONDARY_FG),
            "日期": tk.Label(row_frame, text=date, font=font_manager.get("small"), anchor="w", padx=6,
                             fg=BILL_SECONDARY_FG),
            "修改时间": tk.Label(row_frame, text=b.get("record_time", "-"), font=font_manager.get("small"),
                               anchor="w", padx=6, fg=BILL_SECONDARY_FG),
        }
        # 数据列 grid 配置
        for col in self._data_cols:
            col_idx = self._columns.index(col)
            if col in self._hidden_cols:
                row_frame.grid_columnconfigure(col_idx, minsize=0, weight=0)
            else:
                row_frame.grid_columnconfigure(col_idx, minsize=80, weight=0)
                cells[col].grid(row=0, column=col_idx, sticky="nsew", padx=2, pady=10)

        # 选中行：所有模式都允许（点数据单元 = 选中，点操作按钮 = 触发动作）
        self._bind_row_widgets(row_frame, idx, cells)
        # 右键菜单：cell 上单独绑（不会冒泡到 body）
        # 已完成状态：不绑双击编辑

        return cells

    def _update_row_widgets(self, widgets: dict, idx: int, b) -> None:
        """增量刷新单行：复用现有 widget，只更新文本与颜色（不重建）。

        计算逻辑必须与 _create_row_widgets 完全一致。
        """
        self._ensure_calculations()
        calc = self._calculations[idx]
        content = b.get("content", "")
        note = b.get("note", "")
        date = _format_bill_date(b)

        cat, name = calc.category, calc.name
        orphan = calc.orphan
        billing = calc.billing
        total_val = calc.total

        formula_result_str = ""
        if calc.formula_value is not None:
            formula_result_str = f"{calc.formula_value:.10f}".rstrip("0").rstrip(".") or "0"

        if calc.canonical:
            formula_display = to_display(calc.canonical)
        else:
            formula_display = _format_formula(content, self._op_map)

        if billing.is_per_unit:
            qty_str = formula_display
            price_str = billing.format_price()
        else:
            qty_str = "-"
            price_str = "无单价"

        if isinstance(total_val, (int, float)):
            total_str = f"￥{total_val:.2f}"
            total_color = ORPHAN_FG if orphan else TEXT_PRIMARY
        else:
            total_str = "错误" if content else ""
            total_color = BILL_TERTIARY_FG

        display_name = f"{ORPHAN_PREFIX}{name}" if orphan else name
        if cat and not orphan:
            display_name = f"{cat} - {name}"
        if orphan and cat:
            display_name = f"{ORPHAN_PREFIX}{cat} - {name}（已删除）"

        widgets["#"].config(text=str(idx + 1))
        review_button = widgets.get("审核")
        if review_button is not None:
            review_button.config(
                text="☑" if is_bill_reviewed(b) else "☐",
                fg=SYSTEM_GREEN if is_bill_reviewed(b) else BILL_TERTIARY_FG,
                cursor="hand2" if self._editable else "arrow",
                command=self._review_command(idx) if self._editable else None,
            )
        widgets["工作内容"].config(text=display_name, fg=ORPHAN_FG if orphan else TEXT_PRIMARY)
        widgets["公式"].config(text=qty_str)
        widgets["公式结果"].config(text=formula_result_str)
        widgets["单价"].config(text=price_str, fg=ORPHAN_FG if orphan else TEXT_PRIMARY)
        widgets["金额"].config(text=total_str, fg=total_color)
        widgets["备注"].config(text=note)
        widgets["日期"].config(text=date)
        widgets["修改时间"].config(text=b.get("record_time", "-"))
