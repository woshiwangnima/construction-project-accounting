"""回滚存档列表 widget - 复用 ListViewBase。

列定义：("序号", "上次修改时间", "项目状态", "有效性", "工作数量情况", "账单数", "操作")。
所有数据列随列宽自动换行（wrap_cols），行高随内容动态变化。
列宽可拖拽，权重保存在 app_config。
操作列：删除按钮（无拖动手柄）。
"""
import tkinter as tk

from ..theme import APP_BG, FONT_BODY
from .list_view_base import ListViewBase
from ...project_status import ProjectStatus
from ...backup_inspector import VALIDITY_OK, VALIDITY_HAS_ORPHANS, VALIDITY_INVALID_JSON
from ...config_loader import load_app, save_app
from ...logger import logger

ROLLBACK_COLUMNS = ("序号", "上次修改时间", "项目状态", "有效性", "工作数量情况", "账单数")
ROLLBACK_FULL_COLUMNS = ROLLBACK_COLUMNS + ("操作",)


def load_rollback_weights() -> dict:
    cfg = load_app()
    return cfg.get("rollback_column_widths", {})


def save_rollback_weights(weights: dict) -> None:
    try:
        cfg = load_app()
        cfg["rollback_column_widths"] = dict(weights)
        save_app(cfg)
    except Exception as e:
        logger.warning("保存回滚存档列宽失败: %s", e)


class RollbackListView(ListViewBase):
    """回滚存档列表 widget。"""

    def __init__(self, parent, backups, on_rollback=None, on_delete_backup=None, **kwargs):
        self._backups = list(backups)
        items = [self._backup_to_item(b) for b in self._backups]
        default_weights = load_rollback_weights()
        super().__init__(
            parent,
            columns=ROLLBACK_FULL_COLUMNS,
            default_weights=default_weights or None,
            min_width=60,
            action_col="操作",
            action_col_width=80,
            on_column_resize=save_rollback_weights,
            on_row_activated=on_rollback,
            on_delete=on_delete_backup,
            bg=APP_BG,
            wrap_cols=ROLLBACK_COLUMNS,
            **kwargs,
        )
        self._items = items
        self._render_rows()

    _VALIDITY_MAP = {
        VALIDITY_OK: "✔ 有效",
        VALIDITY_HAS_ORPHANS: "⚠ 含孤儿",
        VALIDITY_INVALID_JSON: "✗ 存档损坏",
    }

    @staticmethod
    def _validity_text(info) -> str:
        if info.validity == VALIDITY_HAS_ORPHANS:
            return f"⚠ 含 {info.orphan_count} 条孤儿账单"
        return RollbackListView._VALIDITY_MAP.get(info.validity, "未知")

    @staticmethod
    def _backup_to_item(info) -> dict:
        status_display = ProjectStatus.from_value(info.status).display_name if info.status else ""
        return {
            "序号": info.file_index,
            "上次修改时间": info.last_modified,
            "项目状态": status_display,
            "有效性": RollbackListView._validity_text(info),
            "工作数量情况": info.trade_summary,
            "账单数": info.bill_summary,
            "_backup_info": info,
        }

    def _create_row_widgets(self, row_frame, idx, item) -> dict:
        cells = {}
        for col_idx, col_key in enumerate(ROLLBACK_COLUMNS):
            cell = tk.Label(
                row_frame, text=item.get(col_key, ""),
                font=FONT_BODY, anchor="w", padx=6,
                wraplength=80, justify="left",
            )
            row_frame.grid_columnconfigure(col_idx, minsize=60, weight=0)
            cell.grid(row=0, column=col_idx, sticky="nsew", padx=2, pady=6)
            cells[col_key] = cell

        for col_key in ROLLBACK_COLUMNS:
            w = cells[col_key]
            w.bind("<Button-1>", lambda e, i=idx: self._on_row_click(i))
            w.bind("<Double-1>", lambda e, i=idx: self._on_row_activated(i) if self._on_row_activated else None)
        return cells
