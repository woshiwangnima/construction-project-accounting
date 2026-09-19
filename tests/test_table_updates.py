"""Incremental updates preserve Qt indexes and invalidate financial inputs."""
import copy
import os
import unittest
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QPersistentModelIndex, Qt
from PySide6.QtGui import QFont
from PySide6.QtWidgets import QApplication

from src.bill_calculation_cache import BillCalculationCache
from src.bill_recompute import calculate_bill
from src.gui.font_manager import font_manager
from src.gui.qt.bill_table import QtBillTable
from src.gui.qt.table_models import QtBillModel, QtWorkerModel, _role_font
from src.gui.theme import REVIEW_BG

_APP = None
TRADES = [
    {"id": "a", "name": "Masonry", "has_unit": True, "unit_price": 3},
    {"id": "b", "name": "Wiring", "has_unit": True, "unit_price": 4},
]


def setUpModule():
    global _APP
    _APP = QApplication.instance() or QApplication([])


def bills():
    return [{"id": str(i), "trade_item_id": "a" if i == 0 else "b",
             "content": "2+3", "reviewed": False} for i in range(3)]


class CalculationCacheTests(unittest.TestCase):
    def test_price_edit_only_recalculates_related_bills(self):
        cache = BillCalculationCache()
        rows, trades = bills(), copy.deepcopy(TRADES)
        before = cache.prepare(rows, trades, {})
        trades[0]["unit_price"] = 7
        with patch("src.bill_calculation_cache.calculate_bill", wraps=calculate_bill) as compute:
            after, total, errors = cache.summarize(rows, trades, {})
        self.assertEqual(compute.call_count, 1)
        self.assertEqual(after[0].total, 35)
        self.assertIs(after[1], before[1])
        self.assertEqual((total, errors), (75, 0))

    def test_review_and_note_edits_reuse_calculations(self):
        cache = BillCalculationCache()
        rows = bills()
        before = cache.prepare(rows, TRADES, {})
        rows[0].update(reviewed=True, note="Checked", record_time="new time")
        with patch("src.bill_calculation_cache.calculate_bill", wraps=calculate_bill) as compute:
            after = cache.prepare(rows, TRADES, {})
        compute.assert_not_called()
        self.assertIs(after[0], before[0])

    def test_in_place_formula_and_operator_changes_invalidate(self):
        cache = BillCalculationCache()
        rows = bills()
        mapping = {"operators": {"*": {"aliases": ["x"]}}}
        cache.prepare(rows, TRADES, mapping)
        rows[0]["content"] = "2x3"
        self.assertEqual(cache.prepare(rows, TRADES, mapping)[0].total, 18)
        mapping["operators"]["*"]["aliases"].clear()
        mapping["operators"]["+"] = {"aliases": ["x"]}
        self.assertEqual(cache.prepare(rows, TRADES, mapping)[0].total, 15)

    def test_deletion_snapshot_and_restoration_invalidate(self):
        cache = BillCalculationCache()
        rows = bills()
        cache.prepare(rows, TRADES, {})
        rows[0]["frozen_total"] = 23
        rows[0]["frozen_snapshot"] = dict(TRADES[0])
        deleted = cache.prepare(rows, TRADES[1:], {})[0]
        self.assertTrue(deleted.orphan)
        self.assertEqual(deleted.total, 23)
        rows[0]["frozen_snapshot"]["name"] = "Frozen label"
        self.assertEqual(cache.prepare(rows, TRADES[1:], {})[0].name, "Frozen label")
        self.assertFalse(cache.prepare(rows, TRADES, {})[0].orphan)

    def test_equivalent_trade_replacement_updates_reference(self):
        cache = BillCalculationCache()
        rows = bills()
        cache.prepare(rows, TRADES, {})
        replacement = copy.deepcopy(TRADES)
        with patch("src.bill_calculation_cache.calculate_bill", wraps=calculate_bill) as compute:
            after = cache.prepare(rows, replacement, {})
        compute.assert_not_called()
        self.assertIs(after[0].trade_item, replacement[0])

    def test_removed_bills_are_evicted(self):
        cache = BillCalculationCache()
        rows = bills()
        cache.prepare(rows, TRADES, {})
        cache.prepare(rows[:1], TRADES, {})
        self.assertEqual(len(cache._entries), 1)
        cache.prepare([], TRADES, {})
        self.assertFalse(cache._entries)


class ModelUpdateTests(unittest.TestCase):
    def setUp(self):
        self.rows = bills()
        self.model = QtBillModel({})
        self.model.set_columns(["#", "审核", "金额"], [])
        self.model.set_data(self.rows, TRADES)
        self.resets = []
        self.model.modelReset.connect(lambda: self.resets.append(True))

    def test_review_emits_only_target_range_and_preserves_index(self):
        index = QPersistentModelIndex(self.model.index(1, 0))
        self.model.row_cells(0)
        retained = self.model.row_cells(2)
        changes = []
        self.model.dataChanged.connect(lambda left, right, *_: changes.append((left.row(), right.row())))
        self.rows[1]["reviewed"] = True
        with patch("src.bill_calculation_cache.calculate_bill", wraps=calculate_bill) as compute:
            self.model.refresh_rows([1])
        compute.assert_not_called()
        self.assertEqual(changes, [(1, 1)])
        self.assertFalse(self.resets)
        self.assertEqual(index.row(), 1)
        self.assertIs(self.model.row_cells(2), retained)
        self.assertEqual(self.model.data(self.model.index(1, 0), Qt.BackgroundRole).color().name(), REVIEW_BG)

    def test_same_columns_and_hidden_changes_do_not_reset(self):
        self.model.set_columns(["#", "审核", "金额"], ["审核"])
        self.assertFalse(self.resets)
        self.model.set_columns(["#", "金额"], [])
        self.assertEqual(len(self.resets), 1)

    def test_insert_and_remove_preserve_surviving_indexes(self):
        index = QPersistentModelIndex(self.model.index(1, 0))
        counts = []
        self.model.rowsAboutToBeInserted.connect(lambda *_: counts.append(self.model.rowCount()))
        self.model.rowsInserted.connect(lambda *_: counts.append(self.model.rowCount()))
        inserted = {"id": "new", "content": "7", "trade_item_id": "a"}
        self.rows.insert(0, inserted)
        self.model.set_data(self.rows, TRADES)
        self.assertEqual(counts, [3, 4])
        self.assertEqual(index.row(), 2)
        self.rows.pop(0)
        self.model.set_data(self.rows, TRADES)
        self.assertEqual(index.row(), 1)
        self.assertFalse(self.resets)

    def test_moves_keep_persistent_index_and_calculation_aligned(self):
        index = QPersistentModelIndex(self.model.index(0, 2))
        movements = []
        self.model.rowsMoved.connect(lambda *_: movements.append(True))
        self.rows.append(self.rows.pop(0))
        self.model.set_data(self.rows, TRADES)
        self.assertEqual(index.row(), 2)
        self.assertEqual(index.data(), "￥15.00")
        self.rows.insert(0, self.rows.pop())
        self.model.set_data(self.rows, TRADES)
        self.assertEqual(index.row(), 0)
        self.assertEqual(len(movements), 2)
        self.assertFalse(self.resets)

    def test_bulk_review_groups_contiguous_rows(self):
        changes = []
        self.model.dataChanged.connect(lambda left, right, *_: changes.append((left.row(), right.row())))
        self.model.refresh_rows([2, 0, 1, 1, -1, 30])
        self.assertEqual(changes, [(0, 2)])

    def test_worker_edit_invalidates_formatted_cells(self):
        model = QtWorkerModel()
        model.set_columns(["名称", "单价"], [])
        rows = copy.deepcopy(TRADES)
        model.set_data(rows)
        self.assertEqual(model.index(0, 1).data(), "￥3.00")
        rows[0]["unit_price"] = 9
        model.set_data(rows)
        self.assertEqual(model.index(0, 1).data(), "￥9.00")


class TableLayoutTests(unittest.TestCase):
    def test_review_keeps_selection_and_does_not_measure_columns(self):
        table = QtBillTable({})
        try:
            rows = bills()
            table.set_columns(["#", "审核", "金额"], [])
            table.update_data(rows, TRADES)
            table.selectRow(1)
            rows[1]["reviewed"] = True
            with patch.object(table, "measure_content_mins") as measure:
                table.refresh_rows([1])
            measure.assert_not_called()
            self.assertEqual(table.selectionModel().selectedRows()[0].row(), 1)
        finally:
            table.deleteLater()

    def test_numeric_font_and_measurement_follow_font_changes(self):
        table = QtBillTable({})
        original_get = font_manager.get
        current = QFont(original_get("body"))
        current.setPixelSize(12)

        def get_font(role):
            return current if role in ("body", "body_bold") else original_get(role)

        try:
            with patch.object(font_manager, "get", side_effect=get_font):
                table.set_columns(["金额"], [])
                table.update_data(bills(), TRADES)
                old_width = table._content_mins["金额"]
                self.assertEqual(_role_font("numeric_bold").pixelSize(), 12)
                current = QFont(current)
                current.setPixelSize(28)
                table.measure_content_mins()
                self.assertEqual(_role_font("numeric_bold").pixelSize(), 28)
                self.assertGreater(table._content_mins["金额"], old_width)
        finally:
            table.deleteLater()


if __name__ == "__main__":
    unittest.main()
