"""「操作」列行内按钮（↑ / ↓ / ✕）的按行悬停显隐。

设计意图：按钮默认不绘制，只有鼠标停在某一行时才在该行显现，
避免整列图标把表格视觉压满；列宽始终保留，所以显隐不会引起列宽跳动。

这里用真实的 delegate.paint 渲染到 QImage 再查像素，
而不是断言"某个私有字段被设成了 True"——后者在绘制逻辑改动后会假绿。
"""
import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QRect, Qt
from PySide6.QtGui import QColor, QImage, QPainter, QStandardItemModel
from PySide6.QtWidgets import QApplication, QStyle, QStyleOptionViewItem

from src.gui.qt.table import RowActionDelegate
from src.gui.theme import DANGER, TEXT_SECONDARY

_ARROW = QColor(TEXT_SECONDARY)   # ↑ / ↓
_CROSS = QColor(DANGER)           # ✕

_APP = None


def setUpModule() -> None:
    global _APP
    _APP = QApplication.instance() or QApplication([])


def _render(delegate: RowActionDelegate, model, row: int,
            size=(160, 40)) -> QImage:
    """把某一行渲染进 QImage，返回图像供像素检查。"""
    img = QImage(size[0], size[1], QImage.Format_ARGB32)
    img.fill(QColor("#ffffff"))
    painter = QPainter(img)
    try:
        option = QStyleOptionViewItem()
        option.rect = QRect(0, 0, size[0], size[1])
        option.state = QStyle.State_Enabled | QStyle.State_Active
        delegate.paint(painter, option, model.index(row, 0))
    finally:
        painter.end()
    return img


def _count_matching(img: QImage, target: QColor, tol: int = 24) -> int:
    """统计与目标色接近的像素数（抗锯齿会让边缘变浅，故用容差）。"""
    hits = 0
    for y in range(img.height()):
        for x in range(img.width()):
            c = img.pixelColor(x, y)
            if (abs(c.red() - target.red()) <= tol
                    and abs(c.green() - target.green()) <= tol
                    and abs(c.blue() - target.blue()) <= tol):
                hits += 1
    return hits


class RowActionDelegateVisibilityTests(unittest.TestCase):
    def setUp(self):
        self.model = QStandardItemModel(3, 1)
        self.delegate = RowActionDelegate()

    def test_nothing_is_drawn_while_mouse_is_outside_the_table(self):
        # 缺省 _hover_row == -1：整列空白
        for row in range(3):
            img = _render(self.delegate, self.model, row)

            self.assertEqual(_count_matching(img, _ARROW), 0)
            self.assertEqual(_count_matching(img, _CROSS), 0)

    def test_buttons_are_drawn_only_on_the_hovered_row(self):
        self.delegate.set_hover_row(1)

        self.assertGreater(_count_matching(_render(self.delegate, self.model, 1), _ARROW), 0)
        self.assertGreater(_count_matching(_render(self.delegate, self.model, 1), _CROSS), 0)
        # 同一时刻其它行必须是空的
        self.assertEqual(_count_matching(_render(self.delegate, self.model, 0), _ARROW), 0)
        self.assertEqual(_count_matching(_render(self.delegate, self.model, 2), _ARROW), 0)

    def test_moving_to_another_row_moves_the_buttons(self):
        self.delegate.set_hover_row(0)
        self.assertGreater(_count_matching(_render(self.delegate, self.model, 0), _ARROW), 0)

        self.delegate.set_hover_row(2)

        self.assertEqual(_count_matching(_render(self.delegate, self.model, 0), _ARROW), 0)
        self.assertGreater(_count_matching(_render(self.delegate, self.model, 2), _ARROW), 0)

    def test_readonly_table_never_draws_buttons(self):
        self.delegate.set_hover_row(1)
        self.delegate.set_enabled(False)

        img = _render(self.delegate, self.model, 1)

        self.assertEqual(_count_matching(img, _ARROW), 0)
        self.assertFalse(self.delegate.is_hovered_row(1))

    def test_rows_beyond_the_model_do_not_draw(self):
        # 鼠标停在表格下方空白处时 indexAt 会给出越界行号，不应误画
        self.delegate.set_hover_row(99)

        for row in range(3):
            self.assertEqual(_count_matching(_render(self.delegate, self.model, row), _ARROW), 0)


class RowActionDelegateHoverStateTests(unittest.TestCase):
    def setUp(self):
        self.delegate = RowActionDelegate()

    def test_set_hover_row_reports_whether_it_changed(self):
        self.assertTrue(self.delegate.set_hover_row(3))
        self.assertFalse(self.delegate.set_hover_row(3))
        self.assertTrue(self.delegate.set_hover_row(-1))

    def test_leaving_the_row_clears_button_level_highlight(self):
        self.delegate._hover = (1, "up")

        self.delegate.set_hover_row(2)

        self.assertIsNone(self.delegate._hover)

    def test_keeping_the_same_row_keeps_button_level_highlight(self):
        self.delegate.set_hover_row(1)
        self.delegate._hover = (1, "up")

        self.delegate.set_hover_row(1)

        self.assertEqual(self.delegate._hover, (1, "up"))

    def test_leaving_the_table_clears_button_level_highlight(self):
        self.delegate.set_hover_row(1)
        self.delegate._hover = (1, "delete")

        self.delegate.set_hover_row(-1)

        self.assertIsNone(self.delegate._hover)

    def test_is_hovered_row_requires_enabled(self):
        self.delegate.set_hover_row(1)

        self.assertTrue(self.delegate.is_hovered_row(1))
        self.assertFalse(self.delegate.is_hovered_row(0))

        self.delegate.set_enabled(False)

        self.assertFalse(self.delegate.is_hovered_row(1))
