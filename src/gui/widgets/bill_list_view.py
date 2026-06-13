"""账单列表 widget - 复用 ListViewBase，仅提供账单特有的单元格渲染。

设计：所有通用逻辑（header、body、列宽拖拽、行选中、↑/↓ 键、操作列）都在
ListViewBase 里，本类只负责把一条账单数据 → 7 个数据列 Label。

依赖 BILLS_COLUMNS / BILLS_DEFAULT_WEIGHTS / BILLS_MIN_WIDTH 来定义列与默认权重。
"""
import tkinter as tk

from ..theme import (
    APP_BG, TEXT_SECONDARY,
    FONT_BODY, FONT_BODY_BOLD, FONT_SMALL,
)
from .list_view_base import ListViewBase
from ..content import (
    BILLS_COLUMNS, BILLS_MIN_WIDTH, BILLS_DEFAULT_WEIGHTS,
    _format_formula, _format_bill_date,
)
from ...billing import read_billing
from ...billing_resolver import (
    resolve_trade_item, resolve_billing, resolve_label, is_orphan,
)
from ...bill_recompute import recompute_bill_total
from ...bill_review import is_bill_reviewed

# 孤儿账单行的文字色（红）+ 前缀图标
ORPHAN_FG = "#c0392b"
ORPHAN_PREFIX = "⚠ "


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
        weights=None,
        editable: bool = True,
        selection_bg: str = "#90cdf4",
        reviewed_bg: str = "#e6fffa",
        **kwargs,
    ):
        # bills 字段名跟 _items 同名（只是 _items 存的是 references），
        # 权重用 BILLS_DEFAULT_WEIGHTS，传给基类的 default_weights 会被基类
        # 自动过滤掉 "操作" 列。
        self._op_map = op_map
        self._trade_items = trade_items or []
        self._on_edit = on_edit
        self._on_review_toggle = on_review_toggle
        self._reviewed_bg = reviewed_bg

        header_click_map = {}
        if on_review_header_toggle is not None and "审核" in BILLS_COLUMNS:
            header_click_map["审核"] = lambda col: on_review_header_toggle()
        if on_sort_by_modified is not None and "修改时间" in BILLS_COLUMNS:
            header_click_map["修改时间"] = lambda col: on_sort_by_modified()

        super().__init__(
            parent,
            columns=BILLS_COLUMNS,
            default_weights=weights or BILLS_DEFAULT_WEIGHTS,
            min_width=BILLS_MIN_WIDTH,
            action_col="操作",
            action_col_width=104,
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
            **kwargs,
        )
        # 存数据（基类 set_items 走 _render_rows，已经会读 self._items）
        self._items = list(bills)
        # 首次构建已经在基类 __init__ 走完了，这里需要重新渲染一次以填账单
        self._render_rows()

    def _row_bg_for_bill(self, idx: int, bill: dict) -> str:
        if is_bill_reviewed(bill):
            return self._reviewed_bg
        return "#f7fafc" if idx % 2 == 1 else "white"

    def set_trade_items(self, trade_items):
        """Trade item 列表变更后调用，重新渲染。"""
        self._trade_items = trade_items or []
        self._render_rows()

    def set_bills(self, bills):
        """账单列表变更后调用，重新渲染。"""
        self._items = list(bills)
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
        if idx is not None and self._on_copy:
            menu.add_command(label="\U0001f4cb 复制此账单", command=lambda i=idx: self._on_copy(i))
        if self._on_paste and (self._paste_enabled is None or self._paste_enabled()):
            # 「粘贴」是否可点：项目已完成时灰显
            allowed = self._paste_allowed is None or self._paste_allowed()
            label = "\U0001f4ce 粘贴账单" if idx is None else "粘贴到末尾"
            menu.add_command(
                label=label, command=lambda i=idx: self._on_paste(i),
                state="normal" if allowed else "disabled",
            )
        if menu.index("end") is None:
            return None
        return menu

    def _create_row_widgets(self, row_frame, idx, b) -> dict:
        """填一行：7 个数据列 Label（操作列由基类自动加 RowActionButtons）。"""
        content = b.get("content", "")
        note = b.get("note", "")
        date = _format_bill_date(b)

        # 名称/类别：从 trade item 实时 join；孤儿走 frozen_snapshot
        cat, name = resolve_label(b, self._trade_items)
        orphan = is_orphan(b, self._trade_items)
        billing = resolve_billing(b, self._trade_items)
        # 合计：实时重算
        total_val = recompute_bill_total(b, self._trade_items, self._op_map)

        if billing.is_per_unit:
            qty_str = _format_formula(content, self._op_map)
            price_str = billing.format_price()
        else:
            qty_str = "-"
            price_str = "无单价"

        if isinstance(total_val, (int, float)):
            total_str = f"￥{total_val:.2f}"
            total_color = ORPHAN_FG if orphan else "#c0392b"
        else:
            total_str = "错误" if content else ""
            total_color = "#999999"

        # 名称带 ⚠ 前缀（孤儿）或 类别 - 名称
        display_name = f"{ORPHAN_PREFIX}{name}" if orphan else name
        if cat and not orphan:
            display_name = f"{cat} - {name}"
        # 孤儿时也加上类别（来自 frozen_snapshot）
        if orphan and cat:
            display_name = f"{ORPHAN_PREFIX}{cat} - {name}（已删除）"
        name_fg = ORPHAN_FG if orphan else TEXT_PRIMARY if False else None

        cells: dict = {
            "#": tk.Label(row_frame, text=str(idx + 1), font=FONT_BODY, anchor="center", padx=4),
            "审核": tk.Button(
                row_frame,
                text="☑" if is_bill_reviewed(b) else "☐",
                font=FONT_BODY_BOLD,
                relief="flat",
                bd=0,
                cursor="hand2" if self._editable else "arrow",
                command=(lambda i=idx, value=not is_bill_reviewed(b): self._on_review_toggle and self._on_review_toggle(i, value))
                if self._editable else None,
            ),
            "工作内容": tk.Label(row_frame, text=display_name, font=FONT_BODY, anchor="w", padx=6,
                                 wraplength=80, justify="left",
                                 fg=ORPHAN_FG if orphan else "#000000"),
            "公式": tk.Label(row_frame, text=qty_str, font=FONT_BODY, anchor="w", padx=6,
                             wraplength=80, justify="left", fg=TEXT_SECONDARY),
            "单价": tk.Label(row_frame, text=price_str, font=FONT_BODY, anchor="w", padx=6,
                             fg=ORPHAN_FG if orphan else "#000000"),
            "金额": tk.Label(row_frame, text=total_str, font=FONT_BODY_BOLD, anchor="e", padx=6,
                             fg=total_color),
            "备注": tk.Label(row_frame, text=note, font=FONT_BODY, anchor="w", padx=6,
                             wraplength=80, justify="left", fg=TEXT_SECONDARY),
            "日期": tk.Label(row_frame, text=date, font=FONT_SMALL, anchor="w", padx=6,
                             fg=TEXT_SECONDARY),
            "修改时间": tk.Label(row_frame, text=b.get("record_time", "-"), font=FONT_SMALL,
                               anchor="w", padx=6, fg=TEXT_SECONDARY),
        }
        # 数据列 grid 配置
        for col_idx, col in enumerate(self._data_cols):
            row_frame.grid_columnconfigure(col_idx, minsize=80, weight=0)
            cells[col].grid(row=0, column=col_idx, sticky="nsew", padx=2, pady=8)

        # 选中行：所有模式都允许（点数据单元 = 选中，点操作按钮 = 触发动作）
        for col_key, w in cells.items():
            w.bind("<Button-1>", lambda *a, i=idx: self._on_row_click(i))
        # 右键菜单：cell 上单独绑（不会冒泡到 body）
        for col_key, w in cells.items():
            w.bind("<Button-3>", lambda *a, i=idx: self._fire_row_right_click(a[0] if a else None, i))
        # 已完成状态：不绑双击编辑
        if self._editable:
            for col_key, w in cells.items():
                w.bind("<Double-1>", lambda *a, i=idx: self._on_edit and self._on_edit(i))

        return cells
