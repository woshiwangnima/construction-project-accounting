import unittest

from src.gui import theme
from src.gui.qt.view_common import SEGMENT_QSS
from src.gui.theme import FontSpec, build_qss


class ThemeQtTests(unittest.TestCase):
    def test_build_qss_contains_all_palette_colors(self):
        qss = build_qss()
        for name in (
            "APP_BG",
            "ACCENT",
            "ACCENT_HOVER",
            "BORDER",
            "TEXT_PRIMARY",
            "TEXT_SECONDARY",
            "TEXT_TERTIARY",
            "HIGHLIGHT_BG",
            "ROW_STRIPE",
            "TABLE_HEADER_BG",
            "TABLE_HEADER_FG",
        ):
            value = getattr(theme, name)
            self.assertIn(value, qss, name)

    def test_build_qss_covers_primary_widget_types(self):
        qss = build_qss()
        for selector in (
            "QMainWindow",
            "QDialog",
            "QPushButton",
            "QLineEdit",
            "QComboBox",
            "QSpinBox",
            "QDateEdit",
            "QTableView",
            "QHeaderView::section",
            "QScrollBar:vertical",
        ):
            self.assertIn(selector, qss, selector)

    def test_tooltip_uses_centralized_high_contrast_pair(self):
        qss = build_qss()
        self.assertNotEqual(theme.TOOLTIP_BG, theme.TOOLTIP_FG)
        self.assertIn(f"background-color: {theme.TOOLTIP_BG}", qss)
        self.assertIn(f"color: {theme.TOOLTIP_FG}", qss)

    def test_segment_local_qss_keeps_global_tooltip_colors(self):
        """嵌套分段容器的局部 QSS 不得冲掉全局 Tooltip 对比度。"""
        self.assertIn(theme.TOOLTIP_QSS, SEGMENT_QSS)
        self.assertIn(f"background-color: {theme.TOOLTIP_BG}", SEGMENT_QSS)
        self.assertIn(f"color: {theme.TOOLTIP_FG}", SEGMENT_QSS)

    def test_font_spec_from_tuple(self):
        spec = FontSpec.from_tuple(theme.FONT_BODY)
        self.assertEqual(spec.family, "Microsoft YaHei UI")
        # FONT_BODY 曾是手写的 13，而 font_manager 的 body 是 14——同一屏两种
        # 正文字号就是这么来的。现在两者都由倍率表派生，body 倍率 1.0。
        self.assertEqual(spec.size, theme.font_px("body", theme.DEFAULT_FONT_SIZE))
        self.assertEqual(spec.weight, "")

    def test_legacy_font_constants_unchanged(self):
        # 这组常量仍按默认基准（14px）派生，值保持不变即为兼容
        self.assertEqual(theme.FONT_TITLE, ("Microsoft YaHei UI", 22, "bold"))
        # APP_BG 于 2026-09-18 由纯白改为暖白（Claude 风色板收敛），随色板走
        self.assertEqual(theme.APP_BG, "#faf9f7")

    def test_font_px_follows_base_size(self):
        """角色字号必须随基准字号等比缩放，不能有第二个基准。"""
        for role in ("title", "heading", "subheading", "body", "small", "amount"):
            small = theme.font_px(role, 14)
            large = theme.font_px(role, 20)
            self.assertGreater(large, small, role)

    def test_font_px_is_clamped(self):
        """倍率算出的字号不许超出可用区间，避免极小/极大值把布局撑坏。"""
        self.assertGreaterEqual(theme.font_px("title", 1), 8)
        self.assertEqual(theme.font_px("title", 999), theme.font_px("title", 30))

    def test_palette_has_no_second_hue(self):
        """色板收敛：不允许出现蓝色系色值（第二色相）。

        历史上 Apple 蓝 #007aff 与 qfluentwidgets 青 #009faa 并存，是界面
        「五颜六色」的根因。现在强调色只有赤陶橙一个色相，这条守住它。
        """
        blues = [
            name
            for name, value in vars(theme).items()
            if isinstance(value, str)
            and len(value) == 7
            and value.startswith("#")
            and int(value[5:7], 16) - int(value[1:3], 16) > 30
        ]
        self.assertEqual(blues, [], f"色板出现蓝色系色值（第二色相）: {blues}")


if __name__ == "__main__":
    unittest.main()
