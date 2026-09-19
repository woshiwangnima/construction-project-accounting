"""工种/分类视图行为混入（自 QtContentArea 抽出）。

只通过 self 访问宿主状态；模块级依赖均为叶子模块，避免循环导入。
"""
import copy
from ...project_service import remove_trades, save_trade

from .icons import (
    ICON_ERASER, ICON_FOLDER_PLUS, ICON_UNDO, icon as ui_icon,
)
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QInputDialog, QLabel, QMenu, QMessageBox

from ...config_loader import load_app, save_app
from ...logger import logger
from ...project_manager import update_project
from ...billing import read_billing
from ...bill_recompute import recompute_bill_total
from ...paste_actions import paste_trade_item, unique_category_after_paste
from ...billing_resolver import resolve_label
from ..theme import DANGER, SYSTEM_GREEN
from ..clipboard import AppClipboard
from ..common.reorder import reorder_subset_by_ids
from .category_utils import (
    BILL_ACTION_COL, WORKER_COLUMNS, _category_maps, _category_name,
    _project_category_names, _trade_item_category_name,
    resolve_worker_column_weights,
)
from .view_common import _build_metric_row


class WorkerViewMixin:
    """工种页：分类主-从、渲染、排序、行内操作、复制/粘贴与分类管理。"""

    def _render_workers(self) -> None:
        if not self.project_data:
            return
        p = self.project_data
        items = p.trade_items
        cats = _project_category_names(p)
        category_maps = _category_maps(p)
        counts: dict[str, int] = {}
        for ti in items:
            cat = _trade_item_category_name(ti, p, category_maps)
            if cat:
                counts[cat] = counts.get(cat, 0) + 1
        ordered_counts = {cat: counts.get(cat, 0) for cat in cats}

        if self._selected_category not in cats:
            self._selected_category = cats[0] if cats else None
        self._category_list.set_categories(ordered_counts)
        self._category_list.set_selected(self._selected_category)
        has_cats = bool(cats)
        self._workers_table.setVisible(has_cats)
        self._workers_empty_hint.setVisible(not has_cats)

        weights = resolve_worker_column_weights(p, self._app_config)
        self._worker_weights = weights
        self._workers_table.set_columns(list(WORKER_COLUMNS), [])
        self._workers_table.set_column_weights(weights, [])
        self._workers_table.update_data(self._get_cat_items())
        self._render_worker_metrics(items)
        self._sync_worker_action_bar()
        self._apply_category_ratio()
    def _render_worker_metrics(self, items: list) -> None:
        """刷新工作类型页的看板：工作类型总数 / 按单价计费 / 未设单价。"""
        labels = getattr(self, "_worker_metric_labels", None)
        if not labels:
            return
        priced = 0
        for ti in items:
            try:
                if read_billing(ti).is_per_unit:
                    priced += 1
            except Exception:
                logger.debug("worker billing read failed", exc_info=True)
        unpriced = len(items) - priced
        labels["kinds"].setText(str(len(items)))
        labels["priced"].setText(str(priced))
        if unpriced:
            labels["unpriced"].setText(f"{unpriced} 个")
            labels["unpriced"].setStyleSheet(
                f"color: {DANGER}; font-weight: bold; border: none;"
            )
        else:
            labels["unpriced"].setText("全部已设")
            labels["unpriced"].setStyleSheet(
                f"color: {SYSTEM_GREEN}; font-weight: bold; border: none;"
            )
    def _get_cat_items(self) -> list:
        """当前选中分类下的工种（直接引用 trade_items 里的元素）。"""
        if not self._selected_category or not self.project_data:
            return []
        category_maps = _category_maps(self.project_data)
        return [
            ti for ti in self.project_data.trade_items
            if _trade_item_category_name(ti, self.project_data, category_maps)
            == self._selected_category
        ]
    def _get_cat_indices(self) -> list[int]:
        """当前分类下每个工种在 trade_items 全局列表里的位置。"""
        if not self._selected_category or not self.project_data:
            return []
        category_maps = _category_maps(self.project_data)
        return [
            i for i, ti in enumerate(self.project_data.trade_items)
            if _trade_item_category_name(ti, self.project_data, category_maps)
            == self._selected_category
        ]
    def _on_category_selected(self, name: str) -> None:
        self._selected_category = name
        self._render_workers()
    def _on_worker_column_resize(self, weights: dict) -> None:
        if not self.current_uuid or self.project_data is None:
            return
        self._worker_weights = dict(weights)
        self.project_data["worker_column_widths"] = dict(weights)
        self._save_bridge.schedule(self.current_uuid, self.project_data)
    def _sort_workers(self, column: str, order: str = "") -> None:
        if not self._editable or not self.project_data:
            return
        items = self.project_data.trade_items
        if column == "单价":
            descending = self._worker_price_sort_descending
            price_positions = [
                i for i, item in enumerate(items)
                if read_billing(item).is_per_unit
            ]
            sorted_priced = sorted(
                (items[i] for i in price_positions),
                key=lambda item: read_billing(item).unit_price,
                reverse=descending,
            )
            result = list(items)
            for pos, item in zip(price_positions, sorted_priced):
                result[pos] = item
            items[:] = result
            self._worker_price_sort_descending = not descending
            self._workers_table.set_sort_indicator(
                "单价", "desc" if descending else "asc"
            )
        elif column == "计费类型":
            descending = self._worker_billing_sort_descending
            with_unit = [item for item in items if read_billing(item).is_per_unit]
            without_unit = [item for item in items if not read_billing(item).is_per_unit]
            ordered = (with_unit + without_unit) if descending else (without_unit + with_unit)
            items[:] = ordered
            self._worker_billing_sort_descending = not descending
            self._workers_table.set_sort_indicator(
                "计费类型", "desc" if descending else "asc"
            )
        else:
            return
        self._save_bridge.schedule(self.current_uuid, self.project_data)
        self._render_workers()
    def _on_worker_action(self, row: int, action: str) -> None:
        if action == "up":
            self._move_trade_item(row, -1)
        elif action == "down":
            self._move_trade_item(row, 1)
        elif action == "delete":
            self._delete_trade_item(row)
    def _move_trade_item(self, idx: int, direction: int) -> None:
        """当前分类内上移/下移：direction=-1 上移，+1 下移。"""
        if not self._editable or not self.project_data:
            return
        cat_indices = self._get_cat_indices()
        if idx < 0 or idx >= len(cat_indices):
            return
        target = idx + direction
        if target < 0 or target >= len(cat_indices):
            return
        items = self.project_data.trade_items
        pos_a, pos_b = cat_indices[idx], cat_indices[target]
        moved_id = items[pos_a].get("id")
        items[pos_a], items[pos_b] = items[pos_b], items[pos_a]
        self._save_bridge.schedule(self.current_uuid, self.project_data)
        self._render_workers()
        self._select_worker_by_id(moved_id)
    def _on_workers_rows_moved(self, rows: list, target: int) -> None:
        if not self._editable or not self.project_data:
            return
        cat_items = self._get_cat_items()
        src = rows[0]
        if src < 0 or src >= len(cat_items):
            return
        moved_id = cat_items[src].get("id")
        visible_ids = [item.get("id", "") for item in cat_items]
        items = self.project_data.trade_items
        new_items = reorder_subset_by_ids(
            items, visible_ids, src, target,
            id_getter=lambda item: item.get("id", ""),
        )
        if new_items == items:
            return
        self.project_data.replace_trade_items(new_items)
        self._save_bridge.schedule(self.current_uuid, self.project_data)
        self._render_workers()
        self._select_worker_by_id(moved_id)
    def _select_worker_by_id(self, item_id: str | None) -> None:
        if not item_id:
            return
        for i, item in enumerate(self._get_cat_items()):
            if item.get("id") == item_id:
                self._workers_table.selectRow(i)
                return
    def _delete_trade_item(self, idx: int) -> None:
        """软删除工作类型：受影响账单冻结为孤儿（与 Tk 一致）。"""
        if not self._editable or not self.project_data:
            return
        cat_indices = self._get_cat_indices()
        if idx < 0 or idx >= len(cat_indices):
            return
        items = self.project_data.trade_items
        item = items[cat_indices[idx]]
        tid = item.get("id", "")
        affected_bills = [
            b for b in self.project_data.bills
            if b.get("trade_item_id") == tid
        ]
        warn_msg = f"删除「{item.get('name', '')}」？"
        if affected_bills:
            warn_msg += (
                f"\n\n有 {len(affected_bills)} 条账单引用此工作项目。"
                "删除后这些账单将显示为「已删除」并保留最后已知金额（不再随单价变化）。"
            )
        if not self._confirm_delete("确认", warn_msg):
            return
        remove_trades(self.project_data, {tid}, self._op_map)
        self._save_bridge.schedule(self.current_uuid, self.project_data)
        self._render_workers()
        self._render_bills()
    def _copy_workers(self, rows: list) -> None:
        if not self.project_data:
            return
        idx = rows[0] if rows else 0
        cat_indices = self._get_cat_indices()
        if idx < 0 or idx >= len(cat_indices):
            return
        items = self.project_data.trade_items
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
        self.toast.emit(f"已复制工作「{payload['name']}」（Ctrl+C）")
    def _paste_workers(self, rows: list) -> None:
        if not self.project_data or not self._editable:
            return
        if not self._clipboard.has_trade_item():
            return
        try:
            entry = self._clipboard.get_trade_item()
        except Exception as e:
            self._error_box("粘贴失败", f"剪贴板数据异常：{e}")
            return
        payload = entry["payload"]
        items = self.project_data.trade_items
        cat_order = self.project_data.category_names
        cat_indices = self._get_cat_indices()

        idx = rows[0] if rows else None
        if idx is not None and 0 <= idx < len(cat_indices):
            global_idx = cat_indices[idx]
            target = items[global_idx]
            if self._confirm_replace(
                "确认替换",
                f"确认用剪贴板内容「{payload.get('name', '')}」替换当前行「{target.get('name', '')}」？",
            ):
                new_ti = paste_trade_item(payload, items, cat_order)
                new_ti["id"] = target["id"]
                new_ti["category"] = target["category"]
                new_ti["category_id"] = target.get("category_id", "")
                save_trade(self.project_data, new_ti)
                self._save_bridge.schedule(self.current_uuid, self.project_data)
                self._render_workers()
                self._render_bills()
                self.toast.emit(f"已替换工作「{new_ti['name']}」")
            return

        # 追加到选中分类尾部（与 Tk 一致：粘贴目标 = 当前选中分类）
        cat = self._selected_category
        if not cat or cat not in cat_order:
            cat = cat_order[0] if cat_order else payload.get("category", "")
        payload["category"] = cat
        new_ti = paste_trade_item(payload, items, cat_order)
        save_trade(self.project_data, new_ti)
        if unique_category_after_paste(new_ti["category"], cat_order):
            cat_order.append(new_ti["category"])
            self.project_data.replace_categories(cat_order)
        self._save_bridge.schedule(self.current_uuid, self.project_data)
        self._render_workers()
        self.toast.emit(f"已粘贴工作「{new_ti['name']}」（Ctrl+V）")
    def _show_worker_mode_menu(self) -> None:
        menu = QMenu(self)
        add_cat = menu.addAction(ui_icon(ICON_FOLDER_PLUS), "添加分类", self._add_category)
        add_cat.setEnabled(self._editable)
        menu.addSeparator()
        restore = menu.addAction(ui_icon(ICON_UNDO), "恢复默认", self._restore_defaults)
        restore.setEnabled(self._editable)
        menu.addSeparator()
        clear = menu.addAction(ui_icon(ICON_ERASER), "清空分类", self._clear_all_categories)
        clear.setEnabled(self._editable)
        menu.exec(self._tab_buttons["workers"].mapToGlobal(
            self._tab_buttons["workers"].rect().bottomLeft()
        ))
    def _edit_trade_item_at(self, idx: int) -> None:
        if not self._editable or not self.project_data:
            return
        cat_indices = self._get_cat_indices()
        if idx < 0 or idx >= len(cat_indices):
            return
        items = self.project_data.trade_items
        ti = items[cat_indices[idx]]
        cats = _project_category_names(self.project_data)
        from .dialogs import EditTradeItemDialog
        dlg = EditTradeItemDialog(
            self, ti, cats, self._op_map,
            on_saved=self._on_trade_item_saved,
        )
        dlg.exec()
    def _on_trade_item_saved(self, updated: dict) -> None:
        if not self.project_data or not self.current_uuid:
            return
        save_trade(self.project_data, updated)
        self._save_bridge.schedule(self.current_uuid, self.project_data)
        self._render_workers()
        self._render_bills()
    def _on_category_menu_action(self, name: str, action: str) -> None:
        if action == "add":
            self._add_category()
        elif action == "edit":
            self._edit_category(name)
        elif action == "up":
            self._move_category(name, -1)
        elif action == "down":
            self._move_category(name, 1)
        elif action == "delete":
            self._delete_category(name)
    def _add_category(self) -> None:
        if not self._editable or not self.project_data:
            return
        name, ok = QInputDialog.getText(self, "添加工作类型", "工作类型名称：")
        if not ok:
            return
        name = name.strip()
        if not name:
            self._error_box("提示", "请输入名称")
            return
        p = self.project_data
        co = p.category_names
        if name not in co:
            co.append(name)
            p.replace_categories(co)
        self._save_bridge.schedule(self.current_uuid, self.project_data)
        self._selected_category = name
        self._render_workers()
    def _edit_category(self, name: str) -> None:
        if not self._editable or not self.project_data:
            return
        new_name, ok = QInputDialog.getText(self, "编辑工作类型", "工作类型名称：", text=name)
        if not ok:
            return
        new_name = new_name.strip()
        if not new_name:
            self._error_box("提示", "请输入名称")
            return
        if new_name == name:
            return
        p = self.project_data
        try:
            p.rename_category(name, new_name)
        except ValueError as exc:
            self._error_box(self.windowTitle(), str(exc))
            return
        self._save_bridge.schedule(self.current_uuid, self.project_data)
        self._selected_category = new_name
        self._render_workers()
        self._render_bills()
    def _move_category(self, name: str, direction: int) -> None:
        """在 category_order 中上移（-1）/下移（+1）一位，保持选中。"""
        if not self._editable or not self.project_data:
            return
        co = list(self.project_data.category_names)
        if name not in co:
            return
        idx = co.index(name)
        target = idx + direction
        if target < 0 or target >= len(co):
            return
        co[idx], co[target] = co[target], co[idx]
        self.project_data.replace_categories(co)
        self._save_bridge.schedule(self.current_uuid, self.project_data)
        self._render_workers()
    def _delete_category(self, name: str) -> None:
        """删除分类：所有受影响账单冻结为孤儿（与 Tk 一致）。"""
        if not self._editable or not self.project_data:
            return
        p = self.project_data
        items = p.trade_items
        category_maps = _category_maps(p)
        deleting = [
            ti for ti in items
            if _trade_item_category_name(ti, p, category_maps) == name
        ]
        deleting_ids = {ti.get("id", "") for ti in deleting}
        affected_bills = [
            b for b in p.bills
            if b.get("trade_item_id") in deleting_ids
        ]
        warn_msg = f"删除分类「{name}」？"
        if deleting:
            warn_msg = f"删除分类「{name}」及其所有工种？"
            if affected_bills:
                warn_msg += (
                    f"\n\n有 {len(affected_bills)} 条账单引用此分类下的工作项目，"
                    "删除后将显示为「已删除」并保留最后已知金额（不再随单价变化）。"
                )
        if not self._confirm_delete("确认", warn_msg):
            return

        remove_trades(p, deleting_ids, self._op_map)
        co = p.category_names
        p.replace_categories([c for c in co if _category_name(c) != name])
        self._save_bridge.schedule(self.current_uuid, self.project_data)
        if self._selected_category == name:
            self._selected_category = None
        self._render_workers()
        self._render_bills()
    def _on_category_splitter_moved(self, _pos: int, _index: int) -> None:
        self._category_ratio_timer.start()
    def _on_category_ratio_timeout(self) -> None:
        if not self._category_splitter or not self.current_uuid:
            return
        sizes = self._category_splitter.sizes()
        total = sizes[0] + sizes[1]
        if total <= 0:
            return
        ratio = round(sizes[0] / total, 6)
        try:
            cfg = load_app()
            old = cfg.get("category_list_width_ratio", 0)
            if abs(old - ratio) > 1e-6:
                cfg["category_list_width_ratio"] = ratio
                save_app(cfg)
        except Exception as e:
            logger.warning("[category] 保存列宽比例失败: %s", e)
    def _apply_category_ratio(self) -> None:
        if not self._category_ratio_pending or not self.current_uuid:
            return
        total = self._category_splitter.width()
        if total <= 0:
            return
        self._category_ratio_pending = False
        ratio = float(self._app_config.get("category_list_width_ratio", 0.22))
        left = int(total * ratio)
        left = max(120, min(left, max(total - 280, 120)))
        self._category_splitter.setSizes([left, max(total - left, 1)])
    def _clear_all_categories(self) -> None:
        """清空所有分类：移除全部工作类型，受影响账单冻结为孤儿（与 Tk 一致）。"""
        if not self._editable or not self.project_data:
            return
        p = self.project_data
        items = p.trade_items
        deleting_ids = {ti.get("id", "") for ti in items}
        affected_bills = [
            b for b in p.bills
            if b.get("trade_item_id") in deleting_ids
        ]
        warn_msg = "确定清空所有分类及其工作数据？此操作不可撤销。"
        if affected_bills:
            warn_msg = (
                f"有 {len(affected_bills)} 条账单引用工作项目，"
                "清空后将显示为「已删除」并保留最后已知金额（不再随单价变化）。\n\n"
                + warn_msg
            )
        if not self._confirm_delete("确认清空", warn_msg):
            return

        remove_trades(p, deleting_ids, self._op_map)
        p.replace_categories([])
        p.replace_trade_items([])
        self._save_bridge.schedule(self.current_uuid, p)
        self._selected_category = None
        self._render_workers()
        self._render_bills()
        self.toast.emit("已清空全部分类")
