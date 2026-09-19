"""表格语义对齐/数字等宽字体 + 模型层整行悬停底色。

- 文本列左对齐、数字列右对齐、分类和状态列居中；
- 数字列用等宽数字字体（Consolas，￥/中文缺字形自动回退系统字体）；
- 模型 ``set_hover_row`` 后 BackgroundRole 在原底色（斑马纹 / 审核绿）
  上向暖灰叠色，与审核底色共存，而不是盖一层实色。
"""

import os
import unittest
from typing import cast

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import Qt
from PySide6.QtGui import QBrush, QFont, QFontMetrics
from PySide6.QtWidgets import QApplication

from src.gui.qt.table import QtBaseTable, cap_utility_column_widths
from src.gui.qt.table_models import (
    _NUMERIC_FAMILY,
    QtBillModel,
    QtWorkerModel,
    _hover_blend,
)
from src.gui.theme import APP_BG, REVIEW_BG, ROW_STRIPE

_APP = None


def setUpModule() -> None:
    global _APP
    _APP = QApplication.instance() or QApplication([])


_BILL_COLUMNS = [
    "#",
    "审核",
    "工作内容",
    "公式",
    "公式结果",
    "单价",
    "金额",
    "备注",
    "日期",
    "修改时间",
    "操作",
]
_WORKER_COLUMNS = ["名称", "单价", "单位", "计费类型", "操作"]

_TRADE_ITEMS = [
    {
        "id": "ti-1",
        "category": "泥瓦工程",
        "name": "砌墙",
        "has_unit": True,
        "unit_price": "12.50",
        "unit": "㎡",
    }
]


def _make_bill_model(bills=None) -> QtBillModel:
    model = QtBillModel({})
    model.set_columns(_BILL_COLUMNS, [])
    model.set_data(
        bills if bills is not None else [{"trade_item_id": "ti-1", "content": "2+1"}],
        _TRADE_ITEMS,
    )
    return model


def _make_worker_model() -> QtWorkerModel:
    model = QtWorkerModel()
    model.set_columns(_WORKER_COLUMNS, [])
    model.set_data(
        [{"name": "砌墙", "has_unit": True, "unit_price": "12.50", "unit": "㎡"}]
    )
    return model


def _cell(model, row: int, col_name: str, role):
    col = model._columns.index(col_name)
    return model.data(model.index(row, col), role)


def _bg_hex(model, row: int, col_name: str) -> str:
    brush = _cell(model, row, col_name, Qt.ItemDataRole.BackgroundRole)
    assert isinstance(brush, QBrush)
    return brush.color().name()


class ResponsiveRowHeightTests(unittest.TestCase):
    def test_row_height_grows_with_large_font(self):
        table = QtBaseTable()
        font = QFont(table.font())
        font.setPixelSize(24)
        table.setFont(font)

        expected = QFontMetrics(font).height() + 16
        self.assertGreaterEqual(table._default_row_height(), expected)
        self.assertEqual(
            table.verticalHeader().defaultSectionSize(),
            table._default_row_height(),
        )
        table.deleteLater()


class ColumnWidthTests(unittest.TestCase):
    def test_utility_columns_are_capped_and_surplus_is_preserved(self):
        original = {
            "#": 140,
            "审核": 220,
            "工作内容": 300,
            "备注": 240,
            "操作": 180,
        }
        visible = list(original)
        result = cap_utility_column_widths(
            original,
            visible,
            {"工作内容": 2.0, "备注": 1.0},
        )

        self.assertEqual(result["#"], 64)
        self.assertEqual(result["审核"], 88)
        self.assertEqual(result["操作"], 120)
        self.assertEqual(sum(result.values()), sum(original.values()))
        self.assertGreater(result["工作内容"] - 300, result["备注"] - 240)

    def test_orphan_bill_uses_text_prefix_instead_of_emoji(self):
        model = _make_bill_model([{"trade_item_id": "missing", "content": "10"}])
        text = _cell(model, 0, "工作内容", Qt.ItemDataRole.DisplayRole)

        self.assertTrue(str(text).startswith("异常 · "))
        self.assertNotIn("⚠", str(text))


class NumericColumnTests(unittest.TestCase):
    """文本左对齐、数字右对齐，分类状态居中，数字继续使用等宽字体。"""

    def test_bill_columns_use_semantic_alignment(self):
        model = _make_bill_model()
        expected = {
            "工作内容": Qt.AlignmentFlag.AlignLeft,
            "备注": Qt.AlignmentFlag.AlignLeft,
            "公式结果": Qt.AlignmentFlag.AlignRight,
            "单价": Qt.AlignmentFlag.AlignRight,
            "金额": Qt.AlignmentFlag.AlignRight,
        }
        for name in _BILL_COLUMNS[:-1]:
            align = cast(
                Qt.AlignmentFlag,
                _cell(model, 0, name, Qt.ItemDataRole.TextAlignmentRole),
            )
            self.assertIsInstance(align, Qt.AlignmentFlag)
            horizontal = expected.get(name, Qt.AlignmentFlag.AlignHCenter)
            self.assertTrue(align & horizontal, f"{name} 水平对齐不符合列语义")
            self.assertTrue(align & Qt.AlignmentFlag.AlignVCenter, f"{name} 应垂直居中")

    def test_bill_numeric_columns_use_monospace_font(self):
        model = _make_bill_model()
        for name in ("公式结果", "单价", "金额"):
            font = cast(QFont, _cell(model, 0, name, Qt.ItemDataRole.FontRole))
            self.assertIsInstance(font, QFont)
            self.assertEqual(font.family(), _NUMERIC_FAMILY, f"{name} 应用等宽数字字体")

    def test_worker_columns_use_semantic_alignment_and_price_monospace(self):
        model = _make_worker_model()
        expected = {
            "名称": Qt.AlignmentFlag.AlignLeft,
            "单价": Qt.AlignmentFlag.AlignRight,
        }
        for name in _WORKER_COLUMNS[:-1]:
            align = cast(
                Qt.AlignmentFlag,
                _cell(model, 0, name, Qt.ItemDataRole.TextAlignmentRole),
            )
            self.assertIsInstance(align, Qt.AlignmentFlag)
            horizontal = expected.get(name, Qt.AlignmentFlag.AlignHCenter)
            self.assertTrue(align & horizontal, f"{name} 水平对齐不符合列语义")
            self.assertTrue(align & Qt.AlignmentFlag.AlignVCenter, f"{name} 应垂直居中")
        font = cast(QFont, _cell(model, 0, "单价", Qt.ItemDataRole.FontRole))
        self.assertIsInstance(font, QFont)
        self.assertEqual(font.family(), _NUMERIC_FAMILY)


class HoverRowTintTests(unittest.TestCase):
    """整行悬停底色：模型层在 BackgroundRole 上叠暖灰。"""

    def test_hover_row_tints_background(self):
        model = _make_bill_model([{"trade_item_id": "ti-1", "content": "2+1"}] * 3)
        self.assertEqual(_bg_hex(model, 0, "金额"), APP_BG.lower())
        self.assertTrue(model.set_hover_row(0))
        self.assertEqual(_bg_hex(model, 0, "金额"), _hover_blend(APP_BG))
        # 相邻行不受影响（第 1 行是斑马纹）
        self.assertEqual(_bg_hex(model, 1, "金额"), ROW_STRIPE.lower())
        model.set_hover_row(-1)
        self.assertEqual(_bg_hex(model, 0, "金额"), APP_BG.lower())

    def test_hover_tint_coexists_with_reviewed_bg(self):
        """审核行 hover 后底色变深但保留绿调（G 仍明显高于 R）。"""
        model = _make_bill_model(
            [{"trade_item_id": "ti-1", "content": "2+1", "reviewed": True}]
        )
        self.assertEqual(_bg_hex(model, 0, "金额"), REVIEW_BG.lower())
        model.set_hover_row(0)
        hovered = _bg_hex(model, 0, "金额")
        self.assertNotEqual(hovered, REVIEW_BG.lower())
        r, g, b = (int(hovered[i : i + 2], 16) for i in (1, 3, 5))
        self.assertGreater(g - r, 3, "审核绿调在 hover 叠色后应仍可辨认")

    def test_worker_model_hover_tint(self):
        model = _make_worker_model()
        base = _bg_hex(model, 0, "名称")
        model.set_hover_row(0)
        self.assertEqual(_bg_hex(model, 0, "名称"), _hover_blend(base))

    def test_set_hover_row_reports_change(self):
        model = _make_worker_model()
        self.assertTrue(model.set_hover_row(0))
        self.assertFalse(model.set_hover_row(0))  # 未变化
        self.assertTrue(model.set_hover_row(-1))

    def test_view_syncs_hover_row_to_model(self):
        """QtBaseTable._set_hover_row 同时驱动 delegate 与模型，行号不漂移。"""
        from src.gui.qt.table import QtBaseTable

        model = _make_worker_model()
        table = QtBaseTable()
        table.bind_model(model)
        table._set_hover_row(0)
        self.assertEqual(model._hover_row, 0)
        self.assertIsNotNone(table._action_delegate)
        assert table._action_delegate is not None
        self.assertEqual(table._action_delegate._hover_row, 0)
        table._set_hover_row(-1)
        self.assertEqual(model._hover_row, -1)
        table.deleteLater()


if __name__ == "__main__":
    unittest.main()
