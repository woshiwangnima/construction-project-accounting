"""工作类型（工种）列表 widget - 复用 ListViewBase。

与「账单管理」同款：可拖拽列宽、可选中行（↑/↓ 键切）、行内上移/下移/删除按钮。

数据项字段：dict，包含 name / unit_price / unit / has_unit。
列定义：("名称", "单价", "单位", "计费类型", "操作")。
"""
import tkinter as tk

from ..theme import (
    APP_BG, FONT_BODY, FONT_BODY_BOLD, TEXT_SECONDARY,
)
from .list_view_base import ListViewBase
from ...billing import read_billing


# 工作类型表完整列（含操作列）
WORKER_FULL_COLUMNS = ("名称", "单价", "单位", "计费类型", "操作")


class WorkerListView(ListViewBase):
    """工种列表 widget。"""

    def __init__(
        self,
        parent,
        items,
        on_activate=None,
        on_move_up=None,
        on_move_down=None,
        on_delete=None,
        on_reorder=None,
        on_column_resize=None,
        weights=None,
        selection_bg: str = "#90cdf4",
        editable: bool = True,
        **kwargs,
    ):
        # 取出默认权重：在原 4 列权重基础上加 "操作" 让基类能 strip
        # 基类会自动 filter "操作"，所以这里传完整 dict 也行，传只含数据列的也行
        default_weights = dict(weights) if weights else None
        super().__init__(
            parent,
            columns=WORKER_FULL_COLUMNS,
            default_weights=default_weights,
            min_width=60,
            action_col="操作",
            action_col_width=104,
            on_column_resize=on_column_resize,
            on_move_up=on_move_up,
            on_move_down=on_move_down,
            on_delete=on_delete,
            on_reorder=on_reorder,
            scroll_id_getter=lambda idx, item=None: (item or {}).get("id"),
            on_row_activated=on_activate,
            selection_bg=selection_bg,
            editable=editable,
            wrap_cols=("名称",),  # 名称列会随列宽自动 wraplength
            **kwargs,
        )
        self._items = list(items)
        self._render_rows()

    def _create_row_widgets(self, row_frame, idx, item) -> dict:
        """填一行：4 个数据列 Label。"""
        name = item.get("name", "")
        billing = read_billing(item)

        if billing.is_per_unit:
            price_text = f"￥{billing.unit_price:.2f}"
            unit_text = billing.unit
            billing_text = "按单价"
            billing_color = TEXT_SECONDARY
        else:
            price_text = "-"
            unit_text = "-"
            billing_text = "无单价"
            billing_color = "#999999"

        cells: dict = {
            "名称": tk.Label(
                row_frame, text=name, font=FONT_BODY, anchor="w", padx=6,
                wraplength=80, justify="left",
            ),
            "单价": tk.Label(
                row_frame, text=price_text, font=FONT_BODY_BOLD, anchor="e", padx=6,
            ),
            "单位": tk.Label(
                row_frame, text=unit_text, font=FONT_BODY, anchor="center", padx=6,
            ),
            "计费类型": tk.Label(
                row_frame, text=billing_text, font=FONT_BODY, anchor="center", padx=6,
                fg=billing_color,
            ),
        }
        # 数据列 grid 配置
        for col_idx, col in enumerate(self._data_cols):
            row_frame.grid_columnconfigure(col_idx, minsize=60, weight=0)
            cells[col].grid(row=0, column=col_idx, sticky="nsew", padx=2, pady=8)

        # 选中行：所有模式都允许（点数据单元 = 选中，点操作按钮 = 触发动作）
        for col_key, w in cells.items():
            w.bind("<Button-1>", lambda e, i=idx: self._on_row_click(i))
        # 右键菜单：cell 上单独绑
        for col_key, w in cells.items():
            w.bind("<Button-3>", lambda e, i=idx: self._fire_row_right_click(e, i))
        # 已完成状态：不绑双击编辑
        if self._editable and self._on_row_activated:
            for col_key, w in cells.items():
                w.bind(
                    "<Double-1>",
                    lambda e, i=idx: self._on_row_activated(i),
                )

        return cells

    def _on_row_right_click(self, event, idx) -> None:
        """工种行 / 空白处右键：弹「复制 / 粘贴」菜单。"""
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
            menu.add_command(label="\U0001f4cb 复制此工作", command=lambda i=idx: self._on_copy(i))
        if self._on_paste and (self._paste_enabled is None or self._paste_enabled()):
            allowed = self._paste_allowed is None or self._paste_allowed()
            label = "\U0001f4ce 粘贴工作类型" if idx is None else "粘贴到末尾"
            menu.add_command(
                label=label, command=lambda i=idx: self._on_paste(i),
                state="normal" if allowed else "disabled",
            )
        if menu.index("end") is None:
            return None
        return menu
