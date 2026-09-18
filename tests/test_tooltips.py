"""统一高对比度 Tooltip 回归测试。"""

import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication, QPushButton

from src.gui.qt.tooltips import ReadableToolTipFilter, set_readable_tooltip
from src.gui.theme import TOOLTIP_BG, TOOLTIP_FG

_APP = None


def setUpModule() -> None:
    global _APP
    _APP = QApplication.instance() or QApplication([])


class ReadableToolTipTests(unittest.TestCase):
    def test_filter_uses_explicit_foreground_and_background(self):
        button = QPushButton("模式")
        tooltip_filter = set_readable_tooltip(button, "模式说明")
        tip = tooltip_filter._createToolTip()
        self.assertIn(TOOLTIP_BG, tip.container.styleSheet())
        self.assertIn(TOOLTIP_FG, tip.label.styleSheet())
        tip.deleteLater()
        button.deleteLater()

    def test_repeated_update_reuses_one_filter(self):
        button = QPushButton("模式")
        first = set_readable_tooltip(button, "第一次")
        second = set_readable_tooltip(button, "第二次")
        self.assertIs(first, second)
        self.assertEqual(button.toolTip(), "第二次")
        filters = button.findChildren(ReadableToolTipFilter)
        self.assertEqual(len(filters), 1)
        button.deleteLater()


if __name__ == "__main__":
    unittest.main()
