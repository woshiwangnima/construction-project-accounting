"""账单视图行为混入（自 QtContentArea 抽出）。

只通过 self 访问宿主状态；模块级依赖均为叶子模块，避免循环导入。
"""
import copy

from .icons import ICON_COLUMNS, ICON_IMAGE, ICON_PLUS, icon as ui_icon
from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import QMenu, QMessageBox

from ...logger import logger
from ...project_manager import update_project
from ...billing import read_billing
from ...bill_recompute import (
    prepare_bill_calculations, recompute_bill_total, summarize_bill_calculations,
)
from ...bill_review import apply_bulk_review, is_bill_reviewed, set_bill_reviewed
from ...paste_actions import paste_bill, unique_category_after_paste
from ...billing_resolver import resolve_label
from ..theme import DANGER, SYSTEM_GREEN
from ..clipboard import AppClipboard
from ..common.reorder import move_item
from .category_utils import (
    BILL_ACTION_COL, _category_maps, _trade_item_category_name,
    resolve_bill_columns,
)
from .view_common import _build_metric_row, _amount_px


class BillViewMixin:
    """账单页：渲染、排序、行内操作、复制/粘贴、列显隐与审核。"""

    def _switch_bill_mode(self, mode: str) -> None:
        if not self.project_data or not self.current_uuid:
            return
        self.project_data["bill_display_mode"] = mode
        if "bill_visible_columns" in self.project_data:
            del self.project_data["bill_visible_columns"]
        self._save_bridge.schedule(self.current_uuid, self.project_data)
        self._render_bills()
    def _render_bills(self) -> None:
        if not self.project_data:
            return
        p = self.project_data
        bills = p.get("bills", []) or []
        trade_items = p.get("trade_items", []) or []
        calculations, total, err_cnt = summarize_bill_calculations(
            bills, trade_items, self._op_map
        )
        columns, weights, hidden = resolve_bill_columns(p, self._app_config)
        self._bill_weights = weights

        cur_mode = p.get("bill_display_mode", "simple")
        if hasattr(self, "_mode_buttons") and cur_mode in self._mode_buttons:
            self._mode_buttons[cur_mode].setChecked(True)

        self._bills_table.set_columns(columns, hidden)
        self._bills_table.set_column_weights(weights, hidden)
        self._bills_table.update_data(bills, trade_items, self._op_map, calculations)

        self._metric_labels["amount"].setText(f"￥{total:.2f}")
        self._metric_labels["count"].setText(str(len(bills)))
        if err_cnt:
            self._metric_labels["errors"].setText(f"{err_cnt} 处错误")
            self._metric_labels["errors"].setStyleSheet(f"color: {DANGER}; font-weight: bold;")
        else:
            self._metric_labels["errors"].setText("无错误")
            self._metric_labels["errors"].setStyleSheet(f"color: {SYSTEM_GREEN}; font-weight: bold;")
        self._bills_empty_hint.setVisible(len(bills) == 0)
        self._sync_action_bar()
    def _on_bill_column_resize(self, weights: dict) -> None:
        if not self.current_uuid or self.project_data is None:
            return
        self._bill_weights = dict(weights)
        self.project_data["bill_column_widths"] = [
            {"name": k, "weight": v} for k, v in weights.items()
        ]
        self._save_bridge.schedule(self.current_uuid, self.project_data)
    def _toggle_bill_review(self, row: int) -> None:
        if not self.project_data:
            return
        bills = self.project_data.get("bills", []) or []
        if row == -1:
            if not self._editable:
                return
            apply_bulk_review(bills)
            self._save_bridge.schedule(self.current_uuid, self.project_data)
            self._render_bills()
            return
        if row < 0 or row >= len(bills):
            return
        set_bill_reviewed(bills[row], not is_bill_reviewed(bills[row]))
        self._save_bridge.schedule(self.current_uuid, self.project_data)
        self._render_bills()
    def _sort_bills(self, column: str, order: str = "") -> None:
        if not self._editable or not self.project_data or column != "修改时间":
            return
        descending = self._bill_sort_descending
        bills = self.project_data.get("bills", []) or []
        bills.sort(key=lambda b: b.get("record_time", ""), reverse=descending)
        self.project_data["bills"] = bills
        self._save_bridge.schedule(self.current_uuid, self.project_data)
        self._bill_sort_descending = not descending
        self._bills_table.set_sort_indicator(
            "修改时间", "desc" if descending else "asc"
        )
        self._render_bills()
    def _on_bill_action(self, row: int, action: str) -> None:
        if action == "up":
            self._move_bill(row, -1)
        elif action == "down":
            self._move_bill(row, 1)
        elif action == "delete":
            self._delete_bill(row)
    def _move_bill(self, idx: int, direction: int) -> None:
        if not self._editable or not self.project_data:
            return
        bills = self.project_data.get("bills", []) or []
        target = idx + direction
        if idx < 0 or target < 0 or target >= len(bills):
            return
        bills[idx], bills[target] = bills[target], bills[idx]
        moved_id = bills[target].get("id")
        self._save_bridge.schedule(self.current_uuid, self.project_data)
        self._render_bills()
        self._select_bill_by_id(moved_id)
    def _on_bills_rows_moved(self, rows: list, target: int) -> None:
        if not self._editable or not self.project_data:
            return
        bills = self.project_data.get("bills", []) or []
        src = rows[0]
        if src < 0 or src >= len(bills):
            return
        # target 为插入下标（与 Tk _reorder_bill 的 to_idx 语义一致），
        # 直接交给 move_item，避免重复 -1 导致下移总差一行。
        to = max(0, min(target, len(bills)))
        if to == src:
            return
        moved_id = bills[src].get("id")
        self.project_data["bills"] = move_item(bills, src, to)
        self._save_bridge.schedule(self.current_uuid, self.project_data)
        self._render_bills()
        self._select_bill_by_id(moved_id)
    def _delete_bill(self, idx: int) -> None:
        if not self._editable or not self.project_data:
            return
        bills = self.project_data.get("bills", []) or []
        if idx < 0 or idx >= len(bills):
            return
        if not self._confirm_delete("确认", f"删除第 {idx + 1} 条记录？"):
            return
        bills.pop(idx)
        self._save_bridge.schedule(self.current_uuid, self.project_data)
        self._render_bills()
    def _select_bill_by_id(self, bill_id: str | None) -> None:
        if not bill_id:
            return
        bills = self.project_data.get("bills", []) or []
        for i, bill in enumerate(bills):
            if bill.get("id") == bill_id:
                self._bills_table.selectRow(i)
                return
    def _copy_bills(self, rows: list) -> None:
        if not self.project_data:
            return
        idx = rows[0] if rows else 0
        bills = self.project_data.get("bills", []) or []
        if idx < 0 or idx >= len(bills):
            return
        bill = bills[idx]
        items = self.project_data.get("trade_items", []) or []
        cat, name = resolve_label(bill, items)
        if not name:
            snap = bill.get("frozen_snapshot")
            name = snap.get("name", "") if isinstance(snap, dict) else ""
        if not name:
            name = bill.get("trade_item_name", "")
        payload = {
            "content": bill.get("content", ""),
            "trade_item_id": bill.get("trade_item_id", ""),
            "trade_item_name_fallback": name,
        }
        for k in ("note", "work_date_type", "work_date_start",
                  "work_date_end", "frozen_snapshot", "frozen_total"):
            if bill.get(k) is not None and bill.get(k) != "":
                payload[k] = bill[k]
        self._clipboard.set_bill(payload, source_ref=self.current_uuid or "")
        self.toast.emit(f"已复制账单 #{idx + 1}（Ctrl+C）")
    def _paste_bills(self, rows: list) -> None:
        if not self.project_data or not self._editable:
            return
        if not self._clipboard.has_bill():
            return
        try:
            entry = self._clipboard.get_bill()
        except Exception as e:
            self._error_box("粘贴失败", f"剪贴板数据异常：{e}")
            return
        payload = entry["payload"]
        items = self.project_data.get("trade_items", []) or []
        new_bill = paste_bill(payload, items)
        bills = self.project_data.setdefault("bills", [])
        bills.append(new_bill)
        self._save_bridge.schedule(self.current_uuid, self.project_data)
        self._render_bills()
        if new_bill.get("trade_item_id"):
            self.toast.emit(f"已粘贴账单到末尾（新行 #{len(bills)}）（Ctrl+V）")
        else:
            self.toast.emit("已粘贴为孤儿账单（目标项目无对应工作项目）（Ctrl+V）")
    def _show_bill_mode_menu(self) -> None:
        if not self.project_data or not self.current_uuid:
            return
        menu = QMenu(self)
        submenu = menu.addMenu(ui_icon(ICON_COLUMNS), "列显示")
        columns, _, hidden = resolve_bill_columns(self.project_data, self._app_config)
        data_cols = [c for c in columns if c != BILL_ACTION_COL]
        visible_set = set(data_cols) - set(hidden)

        label_action = submenu.addAction("列显示（操作列固定）")
        label_action.setEnabled(False)
        submenu.addSeparator()
        for col in data_cols:
            action = submenu.addAction(col)
            action.setCheckable(True)
            action.setChecked(col in visible_set)
            action.triggered.connect(
                lambda _=False, c=col: self._toggle_bill_column_visibility(c)
            )

        menu.addAction(ui_icon(ICON_IMAGE), "导出图片", self._export_image)
        menu.addSeparator()
        add_action = menu.addAction(ui_icon(ICON_PLUS), "添加记录", self._add_bill)
        add_action.setEnabled(self._editable)
        menu.exec(self._tab_buttons["bills"].mapToGlobal(
            self._tab_buttons["bills"].rect().bottomLeft()
        ))
    def _set_bill_visible_columns(self, cols: list[str]) -> None:
        if not self.project_data or not self.current_uuid:
            return
        self.project_data["bill_visible_columns"] = list(cols)
        self._save_bridge.schedule(self.current_uuid, self.project_data)
        self._render_bills()
    def _toggle_bill_column_visibility(self, col: str) -> None:
        columns, _, hidden = resolve_bill_columns(self.project_data, self._app_config)
        visible = set(columns) - set(hidden)
        if col in visible:
            visible.discard(col)
        else:
            visible.add(col)
        ordered = [c for c in columns if c in visible]
        self._set_bill_visible_columns(ordered)
    def _add_bill(self) -> None:
        if not self._editable or not self.project_data:
            return
        from .dialogs import EditBillDialog
        new_bill: dict = {}
        dlg = EditBillDialog(
            self, new_bill, self.project_data, self._op_map,
            on_saved=self._on_bill_saved,
        )
        dlg.exec()
    def _edit_bill(self, row: int) -> None:
        if not self.project_data:
            return
        bills = self.project_data.get("bills", []) or []
        if row < 0 or row >= len(bills):
            return
        from .dialogs import EditBillDialog
        dlg = EditBillDialog(
            self, bills[row], self.project_data, self._op_map,
            on_saved=self._on_bill_saved,
        )
        dlg.exec()
    def _on_bill_saved(self, updated: dict) -> None:
        if not self.project_data or not self.current_uuid:
            return
        from ...project_manager import ensure_bill_id
        bills = self.project_data.get("bills", []) or []
        bill_id = updated.get("id")
        if bill_id:
            for i, b in enumerate(bills):
                if b.get("id") == bill_id:
                    bills[i] = updated
                    break
            else:
                bills.append(updated)
        else:
            ensure_bill_id(updated)
            bills.append(updated)
        self.project_data["bills"] = bills
        self._save_bridge.schedule(self.current_uuid, self.project_data)
        self._render_bills()
