import unittest

from src.gui import theme
from src.gui.theme import FontSpec, build_qss


class ThemeQtTests(unittest.TestCase):
    def test_build_qss_contains_all_palette_colors(self):
        qss = build_qss()
        for name in (
            "APP_BG", "ACCENT", "ACCENT_HOVER", "BORDER", "TEXT_PRIMARY",
            "TEXT_SECONDARY", "TEXT_TERTIARY", "HIGHLIGHT_BG", "ROW_STRIPE",
            "TABLE_HEADER_BG", "TABLE_HEADER_FG",
        ):
            value = getattr(theme, name)
            self.assertIn(value, qss, name)

    def test_build_qss_covers_primary_widget_types(self):
        qss = build_qss()
        for selector in (
            "QMainWindow", "QDialog", "QPushButton", "QLineEdit",
            "QComboBox", "QSpinBox", "QDateEdit", "QTableView",
            "QHeaderView::section", "QScrollBar:vertical",
        ):
            self.assertIn(selector, qss, selector)

    def test_font_spec_from_tuple(self):
        spec = FontSpec.from_tuple(theme.FONT_BODY)
        self.assertEqual(spec.family, "Microsoft YaHei UI")
        self.assertEqual(spec.size, 13)
        self.assertEqual(spec.weight, "")

    def test_legacy_font_constants_unchanged(self):
        self.assertEqual(theme.FONT_TITLE, ("Microsoft YaHei UI", 22, "bold"))
        self.assertEqual(theme.APP_BG, "#ffffff")


if __name__ == "__main__":
    unittest.main()
