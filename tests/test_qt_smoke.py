"""Qt 界面层无头（offscreen）冒烟测试。

离屏实例化 MainWindow → QtContentArea（账单/工种表格、分类主-从窗格），
模拟页签切换、排序、审核、复制粘贴、拖拽重排、动作按钮、分类管理、
列显隐与异步保存等主要交互，断言模型与业务数据变化。不依赖显示器。

隔离策略：每个测试独立临时数据目录（CPA_PROJECTS_DIR / CPA_BACKUPS_DIR /
CPA_CONFIG_DIR / CPA_LOG_DIR 指向临时目录），测试后清理，不污染用户数据。

难以无头覆盖的项：真实 QDrag 鼠标拖拽手势、模态对话框按键（QInputDialog /
QMessageBox 已 mock）、字体/像素级渲染、跨进程重启的窗口几何持久化。
"""
import copy
import json
import os
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication

from src.bill_review import is_bill_reviewed
from src.gui import theme
from src.gui.font_manager import font_manager
from src.gui.qt.content import QtContentArea
from src.gui.qt.main_window import MainWindow
from src.gui.widgets.reorder import move_item
from src.project_manager import get_project, project_file_path, update_project

_FONT_MANAGER_SNAPSHOT: dict | None = None


def setUpModule() -> None:
    """强制 Qt 模式字体。

    完整套件（unittest discover）运行时，Tk 测试可能已用 Tk 模式初始化了
    font_manager 单例，随后的 init_qt() 会早退，Qt 控件 setFont 将收到
    tk.font.Font 而报 TypeError。这里先快照单例状态，再强制以 Qt 模式重建。
    """
    global _FONT_MANAGER_SNAPSHOT
    _FONT_MANAGER_SNAPSHOT = {
        "_root": font_manager._root,
        "_fonts": font_manager._fonts,
        "_colors": font_manager._colors,
        "_initialized": font_manager._initialized,
        "_mode": font_manager._mode,
        "_qt_refresh_callback": font_manager._qt_refresh_callback,
    }
    font_manager._root = None
    font_manager._fonts = {}
    font_manager._colors = {}
    font_manager._initialized = False
    font_manager._mode = None
    font_manager.init_qt()


def tearDownModule() -> None:
    """还原 font_manager 单例，避免影响完整套件中后续的 Tk 测试。"""
    global _FONT_MANAGER_SNAPSHOT
    if _FONT_MANAGER_SNAPSHOT is not None:
        for attr, value in _FONT_MANAGER_SNAPSHOT.items():
            setattr(font_manager, attr, value)
        _FONT_MANAGER_SNAPSHOT = None

PROJECT_UUID = "11111111-2222-3333-4444-555555555555"
PROJECT_NAME = "冒烟测试项目"

_INIT_CATEGORIES = [
    {"id": "cat-a", "name": "泥瓦工程"},
    {"id": "cat-b", "name": "水电工程"},
]

_INIT_TRADE_ITEMS = [
    {"id": "ti-a1", "category_id": "cat-a", "category": "泥瓦工程",
     "name": "砌墙", "has_unit": True, "unit_price": "10", "unit": "㎡"},
    {"id": "ti-a2", "category_id": "cat-a", "category": "泥瓦工程",
     "name": "贴砖", "has_unit": True, "unit_price": "20", "unit": "㎡"},
    {"id": "ti-a3", "category_id": "cat-a", "category": "泥瓦工程",
     "name": "抹灰", "has_unit": False, "unit_price": "0", "unit": ""},
    {"id": "ti-b1", "category_id": "cat-b", "category": "水电工程",
     "name": "布线", "has_unit": True, "unit_price": "15", "unit": "m"},
    {"id": "ti-b2", "category_id": "cat-b", "category": "水电工程",
     "name": "插座安装", "has_unit": True, "unit_price": "25", "unit": "个"},
]

_INIT_BILLS = [
    {"id": "bill-1", "trade_item_id": "ti-a1", "content": "2+1",
     "record_time": "2026-01-03 10:00:00"},
    {"id": "bill-2", "trade_item_id": "ti-a2", "content": "3",
     "record_time": "2026-01-01 10:00:00"},
    {"id": "bill-3", "trade_item_id": "ti-b1", "content": "2+2",
     "record_time": "2026-01-02 10:00:00"},
]

CATEGORIES = copy.deepcopy(_INIT_CATEGORIES)
TRADE_ITEMS = copy.deepcopy(_INIT_TRADE_ITEMS)
BILLS = copy.deepcopy(_INIT_BILLS)

ENV_KEYS = ("CPA_PROJECTS_DIR", "CPA_BACKUPS_DIR", "CPA_CONFIG_DIR", "CPA_LOG_DIR")


def _reset_global_test_data():
    global CATEGORIES, TRADE_ITEMS, BILLS
    CATEGORIES.clear()
    CATEGORIES.extend(copy.deepcopy(_INIT_CATEGORIES))
    TRADE_ITEMS.clear()
    TRADE_ITEMS.extend(copy.deepcopy(_INIT_TRADE_ITEMS))
    BILLS.clear()
    BILLS.extend(copy.deepcopy(_INIT_BILLS))


def _build_project_data() -> dict:
    _reset_global_test_data()
    return copy.deepcopy({
        "project_uuid": PROJECT_UUID,
        "name": PROJECT_NAME,
        "status": "editing",
        "created_at": "2026-01-01",
        "last_modified": "2026-01-01 00:00:00",
        "description": "",
        "project_date_type": "无时间",
        "project_date_start": "",
        "project_date_end": "",
        "category_order": CATEGORIES,
        "trade_items": TRADE_ITEMS,
        "bills": BILLS,
    })


def _app() -> QApplication:
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


class QtSmokeBase(unittest.TestCase):
    """每个测试独立临时数据目录 + 全新 MainWindow。"""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory(
            prefix="cpa_qt_smoke_", ignore_cleanup_errors=True
        )
        root = Path(self._tmp.name)
        self._env_backup = {}
        for key in ENV_KEYS:
            sub = key[len("CPA_"):].lower()
            (root / sub).mkdir()
            self._env_backup[key] = os.environ.get(key)
            os.environ[key] = str(root / sub)
        self.app = _app()
        from src.gui.clipboard import AppClipboard
        AppClipboard().clear()
        from src.project_manager import _invalidate_list_cache
        _invalidate_list_cache()
        update_project(PROJECT_UUID, _build_project_data())
        self.window = MainWindow()
        self.window.show()
        self.app.processEvents()
        self.content = self.window.content
        self.content.load_project(PROJECT_UUID)
        self.content._clipboard.clear()
        self.app.processEvents()

    def tearDown(self):
        try:
            self.content.flush_project_save(5)
        finally:
            self.window._on_close()
            self.window.deleteLater()
            self.app.processEvents()
            time.sleep(0.2)
            for key in ENV_KEYS:
                old = self._env_backup.get(key)
                if old is None:
                    os.environ.pop(key, None)
                else:
                    os.environ[key] = old
            self._tmp.cleanup()

    # ── 便捷访问 ────────────────────────────────────────────────────────────

    @property
    def bill_model(self):
        return self.content._bills_table._model

    @property
    def worker_model(self):
        return self.content._workers_table._model

    def bill_ids(self) -> list[str]:
        return [b.get("id") for b in self.bill_model._rows]

    def worker_ids(self) -> list[str]:
        return [w.get("id") for w in self.worker_model._rows]

    def worker_names(self) -> list[str]:
        return [w.get("name") for w in self.worker_model._rows]

    def show_workers_tab(self) -> None:
        self.content._tab_buttons["workers"].click()
        self.app.processEvents()

    def cell_bg(self, model, row: int, col: int):
        brush = model.data(model.index(row, col), Qt.BackgroundRole)
        return brush.color().name().upper() if brush else None


class StartupAndTabTests(QtSmokeBase):
    def test_bills_tab_renders_all_rows_and_metrics(self):
        self.assertEqual(self.bill_model.rowCount(), 3)
        self.assertEqual(self.bill_model.columnCount(), 11)
        self.assertEqual(self.content._metric_labels["count"].text(), "3")
        self.assertIn("￥", self.content._metric_labels["amount"].text())

    def test_workers_tab_renders_selected_category_rows(self):
        self.show_workers_tab()
        self.assertEqual(self.worker_model.rowCount(), 3)
        self.assertEqual(self.worker_model.columnCount(), 5)
        self.assertEqual(self.worker_ids(), ["ti-a1", "ti-a2", "ti-a3"])
        self.assertEqual(self.content._category_list.get_selected(), "泥瓦工程")
        self.assertEqual(self.content._category_list._names, ["泥瓦工程", "水电工程"])

    def test_tab_switch_flips_stack_and_buttons(self):
        self.assertEqual(self.content._stack.currentWidget(), self.content._bills_page)
        self.assertTrue(self.content._tab_buttons["bills"].isChecked())
        self.show_workers_tab()
        self.assertEqual(self.content._stack.currentWidget(), self.content._workers_page)
        self.assertTrue(self.content._tab_buttons["workers"].isChecked())
        self.assertFalse(self.content._tab_buttons["bills"].isChecked())
        self.content._tab_buttons["bills"].click()
        self.assertEqual(self.content._stack.currentWidget(), self.content._bills_page)
        self.assertEqual(self.bill_model.rowCount(), 3)

    def test_sidebar_chain_loads_project(self):
        self.assertIn(PROJECT_UUID, self.window.sidebar._item_widgets)
        self.assertEqual(self.content.current_uuid, PROJECT_UUID)
        self.assertEqual(self.content._header_name_lbl.text(), PROJECT_NAME)


class SortingTests(QtSmokeBase):
    def test_bill_sort_by_modified_time_flips_first_row(self):
        self.assertEqual(self.bill_ids(), ["bill-1", "bill-2", "bill-3"])
        self.content._sort_bills("修改时间", "asc")
        self.assertEqual(self.bill_ids(), ["bill-2", "bill-3", "bill-1"])
        self.content._sort_bills("修改时间", "asc")
        self.assertEqual(self.bill_ids(), ["bill-1", "bill-3", "bill-2"])

    def test_worker_sort_by_unit_price_flips_first_row(self):
        # 排序作用于全局 trade_items（有单价的工种按价格重排，无单价者原位不动）
        self.content._sort_workers("单价", "asc")
        self.assertEqual(self.worker_names(), ["砌墙", "抹灰", "贴砖"])
        self.content._sort_workers("单价", "asc")
        self.assertEqual(self.worker_names(), ["贴砖", "抹灰", "砌墙"])

    def test_sort_requested_signal_reaches_content(self):
        self.content._bills_table.sort_requested.emit("修改时间", "asc")
        self.assertEqual(self.bill_ids(), ["bill-2", "bill-3", "bill-1"])


class ReviewToggleTests(QtSmokeBase):
    def test_single_bill_review_toggle_updates_model_and_data(self):
        review_col = self.bill_model._columns.index("审核")
        self.assertNotEqual(
            self.cell_bg(self.bill_model, 0, review_col), theme.REVIEW_BG.upper()
        )
        self.assertEqual(
            self.bill_model.data(self.bill_model.index(0, review_col), Qt.DisplayRole), "☐"
        )
        self.content._toggle_bill_review(0)
        self.assertTrue(is_bill_reviewed(self.content.project_data.get("bills")[0]))
        self.assertEqual(self.cell_bg(self.bill_model, 0, review_col), theme.REVIEW_BG.upper())
        self.assertEqual(
            self.bill_model.data(self.bill_model.index(0, review_col), Qt.DisplayRole), "☑"
        )
        self.content._toggle_bill_review(0)
        self.assertFalse(is_bill_reviewed(self.content.project_data.get("bills")[0]))
        self.assertEqual(self.cell_bg(self.bill_model, 0, review_col), theme.APP_BG.upper())

    def test_bulk_review_marks_all_rows(self):
        self.content._toggle_bill_review(-1)
        for bill in self.content.project_data.get("bills"):
            self.assertTrue(is_bill_reviewed(bill))


class CopyPasteTests(QtSmokeBase):
    def test_bill_copy_paste_appends_row(self):
        self.content._copy_bills([0])
        self.assertTrue(self.content._clipboard.has_bill())
        self.content._paste_bills([])
        self.assertEqual(self.bill_model.rowCount(), 4)
        self.assertEqual(self.bill_ids()[3], self.bill_ids()[-1])
        pasted = self.content.project_data.get("bills")[-1]
        self.assertEqual(pasted.get("content"), "2+1")
        self.assertEqual(pasted.get("trade_item_id"), "ti-a1")

    def test_worker_copy_paste_appends_to_selected_category(self):
        self.show_workers_tab()
        self.content._copy_workers([0])
        self.assertTrue(self.content._clipboard.has_trade_item())
        self.content._paste_workers([])
        self.assertEqual(self.worker_model.rowCount(), 4)
        self.assertEqual(self.worker_names()[-1], "砌墙 副本")
        self.assertEqual(len(self.content.project_data.get("category_order")), 2)

    def test_paste_without_copy_is_noop(self):
        self.content._paste_bills([])
        self.assertEqual(self.bill_model.rowCount(), 3)


class RowMoveTests(QtSmokeBase):
    def test_bill_rows_moved_signal_reorders_and_selects(self):
        self.bill_model.rows_moved.emit([0], 3)
        self.app.processEvents()
        self.assertEqual(self.bill_ids(), ["bill-2", "bill-3", "bill-1"])
        selected = self.content._bills_table.selectionModel().selectedRows()
        self.assertEqual([self.bill_ids()[i.row()] for i in selected], ["bill-1"])

    def test_worker_rows_moved_reorders_subset_in_place(self):
        self.show_workers_tab()
        self.worker_model.rows_moved.emit([0], 3)
        self.app.processEvents()
        self.assertEqual(self.worker_ids(), ["ti-a2", "ti-a3", "ti-a1"])
        global_ids = [ti.get("id") for ti in self.content.project_data.get("trade_items")]
        self.assertEqual(global_ids, ["ti-a2", "ti-a3", "ti-a1", "ti-b1", "ti-b2"])

    def test_business_move_item_helper(self):
        # to_idx 为“插入下标”语义（与 Tk 拖拽一致）：0→3 表示插到第 3 位之前
        self.assertEqual(move_item([1, 2, 3, 4], 0, 3), [2, 3, 1, 4])
        self.assertEqual(move_item([1, 2, 3, 4], 2, 0), [3, 1, 2, 4])


class ActionButtonTests(QtSmokeBase):
    def test_bill_action_move_down(self):
        self.content._bills_table.action_triggered.emit(0, "down")
        self.assertEqual(self.bill_ids(), ["bill-2", "bill-1", "bill-3"])

    def test_bill_action_move_up(self):
        self.content._bills_table.action_triggered.emit(1, "up")
        self.assertEqual(self.bill_ids(), ["bill-2", "bill-1", "bill-3"])

    def test_bill_action_delete_removes_row(self):
        with patch.object(QtContentArea, "_confirm_delete", return_value=True):
            self.content._bills_table.action_triggered.emit(0, "delete")
        self.assertEqual(self.bill_model.rowCount(), 2)

    def test_worker_action_move_up(self):
        self.show_workers_tab()
        self.content._workers_table.action_triggered.emit(1, "up")
        self.assertEqual(self.worker_names(), ["贴砖", "砌墙", "抹灰"])

    def test_worker_action_delete_freezes_affected_bills(self):
        self.show_workers_tab()
        with patch.object(QtContentArea, "_confirm_delete", return_value=True):
            self.content._workers_table.action_triggered.emit(0, "delete")
        self.assertEqual(self.worker_model.rowCount(), 2)
        self.assertEqual(len(self.content.project_data.get("trade_items")), 4)
        frozen = self.content.project_data.get("bills")[0]
        self.assertEqual(frozen.get("trade_item_id"), "")
        self.assertEqual(frozen.get("frozen_snapshot", {}).get("name"), "砌墙")
        self.assertTrue(frozen.get("_needs_attention"))
        self.assertEqual(self.content.project_data.get("bills")[1].get("trade_item_id"), "ti-a2")


class CategoryPaneTests(QtSmokeBase):
    def test_select_category_filters_worker_rows(self):
        self.show_workers_tab()
        self.content._on_category_selected("水电工程")
        self.assertEqual(self.worker_ids(), ["ti-b1", "ti-b2"])
        self.assertEqual(self.content._category_list.get_selected(), "水电工程")

    def test_rename_category_syncs_order_and_items(self):
        self.show_workers_tab()
        with patch("src.gui.qt.content.QInputDialog.getText",
                   return_value=("防水工程", True)):
            self.content._edit_category("水电工程")
        raw_cats = self.content.project_data.get("category_order", [])
        names = [c["name"] if isinstance(c, dict) else (c.name if hasattr(c, "name") else str(c)) for c in raw_cats]
        self.assertEqual(names, ["泥瓦工程", "防水工程"])
        items = self.content.project_data.get("trade_items")
        self.assertEqual(items[3].get("category"), "防水工程")
        self.assertEqual(self.content._selected_category, "防水工程")
        self.assertEqual(self.worker_ids(), ["ti-b1", "ti-b2"])

    def test_add_category_appends_to_order(self):
        self.show_workers_tab()
        with patch("src.gui.qt.content.QInputDialog.getText",
                   return_value=("新增分类", True)):
            self.content._add_category()
        raw_cats = self.content.project_data.get("category_order", [])
        names = [c["name"] if isinstance(c, dict) else (c.name if hasattr(c, "name") else str(c)) for c in raw_cats]
        self.assertEqual(names, ["泥瓦工程", "水电工程", "新增分类"])
        self.assertEqual(self.content._selected_category, "新增分类")
        self.assertEqual(self.worker_model.rowCount(), 0)

    def test_delete_category_freezes_bills_and_removes_items(self):
        self.show_workers_tab()
        with patch.object(QtContentArea, "_confirm_delete", return_value=True):
            self.content._delete_category("泥瓦工程")
        self.assertEqual([c["name"] if isinstance(c, dict) else c for c in self.content.project_data.get("category_order")], ["水电工程"])
        self.assertEqual(len(self.content.project_data.get("trade_items")), 2)
        self.assertEqual(self.worker_ids(), ["ti-b1", "ti-b2"])
        frozen = self.content.project_data.get("bills")[0]
        self.assertEqual(frozen.get("trade_item_id"), "")
        self.assertEqual(frozen.get("frozen_snapshot", {}).get("name"), "砌墙")


class ColumnLayoutTests(QtSmokeBase):
    def test_set_visible_columns_hides_others(self):
        self.content._set_bill_visible_columns(["审核", "工作内容"])
        model = self.bill_model
        for name in ("金额", "修改时间", "公式"):
            col = model._columns.index(name)
            self.assertTrue(self.content._bills_table.isColumnHidden(col), name)
        action_col = model._columns.index("操作")
        self.assertFalse(self.content._bills_table.isColumnHidden(action_col))

    def test_set_column_weights_no_exception(self):
        weights = dict(self.content._bill_weights)
        self.content._bills_table.set_column_weights(weights, [])
        self.content._bills_table.set_column_weights(weights, ["#", "修改时间"])
        model = self.bill_model
        self.assertTrue(
            self.content._bills_table.isColumnHidden(model._columns.index("修改时间"))
        )

    def test_display_mode_preset_removed(self):
        """三预设循环(Alt+D)已移除：默认速览 5 列，无 toggle_bill_display_mode。"""
        self.assertFalse(
            hasattr(self.content, "toggle_bill_display_mode"),
            "三预设循环快捷键已按设计移除",
        )
        model = self.bill_model
        self.assertTrue(
            self.content._bills_table.isColumnHidden(model._columns.index("修改时间"))
        )
        self.assertFalse(
            self.content._bills_table.isColumnHidden(model._columns.index("审核"))
        )
        self.assertFalse(
            self.content._bills_table.isColumnHidden(model._columns.index("金额"))
        )


class SavePersistenceTests(QtSmokeBase):
    def test_flush_persists_edited_project_to_disk(self):
        self.content._copy_bills([0])
        self.content._paste_bills([])
        self.assertTrue(self.content.flush_project_save(5))
        path = project_file_path(PROJECT_UUID)
        self.assertTrue(path.is_file())
        on_disk = json.loads(path.read_text(encoding="utf-8"))
        self.assertEqual(len(on_disk["bills"]), 4)
        reloaded = get_project(PROJECT_UUID)
        self.assertEqual(len(reloaded.get("bills")), 4)

    def test_status_toggle_persists(self):
        self.assertEqual(self.content.get_project_status().value, "editing")
        self.content._toggle_status()
        self.assertEqual(self.content.get_project_status().value, "done")
        self.assertTrue(self.content.flush_project_save(5))
        reloaded = get_project(PROJECT_UUID)
        self.assertEqual(reloaded.get("status"), "done")

    def test_save_bridge_collapses_multiple_edits(self):
        bills = self.content.project_data.get("bills")
        for content in ("5", "6", "7"):
            bills[0]["content"] = content
            self.content._save_bridge.schedule(PROJECT_UUID, self.content.project_data)
        self.assertTrue(self.content.flush_project_save(5))
        reloaded = get_project(PROJECT_UUID)
        self.assertEqual(reloaded.get("bills")[0].get("content"), "7")


if __name__ == "__main__":
    unittest.main()
