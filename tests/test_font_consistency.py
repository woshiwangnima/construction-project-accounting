"""字号单一真源的守护测试。

背景（2026-09-18）：字号曾有三套来源——

1. ``build_qss()`` 里的插值变量；
2. ``font_manager`` 的角色倍率表（与 1 各写一份）；
3. 散落在 16 个文件里的 39 处 ``font-size: Npx`` 字面量。

第 3 类不接任何配置，用户在设置里改「默认字号」时纹丝不动；字体设置面板
里的字号输入框也是哑炮（提交 72、实际出来 24）。这个文件把约束钉住。
"""

import os
import pathlib
import re
import unittest
from typing import cast

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtGui import QFont
from PySide6.QtWidgets import QApplication

from src.gui import font_manager as fm
from src.gui import theme
from src.gui.font_manager import ROLE_KEYS, FontManager, font_manager
from src.gui.qt.dialogs.settings.font_panel import _build_preview_font

_APP = QApplication.instance() or QApplication([])

GUI_ROOT = pathlib.Path(__file__).resolve().parent.parent / "src" / "gui"

# font-size 后面直接跟数字 = 写死的字号
HARDCODED_PX = re.compile(r"font-size:\s*\d+px")
# font-size 后面直接跟函数名 = 忘了包 {}，QSS 会静默忽略整条声明
BARE_CALL = re.compile(r"font-size:\s*font_px")


def _scan(pattern: re.Pattern) -> list:
    """扫描 src/gui 下的源码，返回命中位置（跳过文档示例行）。"""
    hits = []
    for path in sorted(GUI_ROOT.rglob("*.py")):
        text = path.read_text(encoding="utf-8")
        for lineno, line in enumerate(text.splitlines(), 1):
            if pattern.search(line) is None:
                continue
            if "``" in line:  # docstring 里的写法示例，不是真代码
                continue
            hits.append(f"{path.relative_to(GUI_ROOT)}:{lineno}")
    return hits


class FontSingleSourceTests(unittest.TestCase):
    def test_font_manager_reuses_theme_multipliers(self):
        """倍率表只有一张，不许再各写一份。"""
        self.assertIs(fm._ROLE_SIZE_MULTIPLIERS, theme.FONT_SIZE_MULTIPLIERS)

    def test_manager_and_font_px_agree(self):
        """font_manager 的 QFont 与 font_px() 必须给出同一字号。

        这两条通道分别喂养 setFont 与 QSS，一旦分叉，同一屏里就会出现
        两种大小的正文。
        """
        font_manager.init_qt()
        # 其他测试可能改过临时配置；比较前按当前配置重建字体缓存。
        font_manager.refresh()
        for role in ROLE_KEYS:
            self.assertEqual(
                cast(QFont, font_manager.get(role)).pixelSize(),
                theme.font_px(role),
                f"{role} 的两条通道字号不一致",
            )

    def test_settings_preview_uses_pixel_size(self):
        """字体面板预览必须与实际控件一样使用 px，而不是 QFont 的 pt。"""
        preview = _build_preview_font(
            {
                "family": "Microsoft YaHei UI",
                "size": 18,
                "bold": True,
                "italic": False,
                "underline": False,
                "overstrike": False,
            }
        )
        self.assertEqual(preview.pixelSize(), 18)
        self.assertEqual(preview.pointSize(), -1)

    def test_role_multiplier_override_wins(self):
        """字体面板写回的 multiplier 必须真正生效（曾经被直接丢弃）。"""
        self.assertEqual(
            FontManager._resolve_multiplier("title", {"multiplier": 2.0}, 14), 2.0
        )

    def test_legacy_size_override_is_honoured(self):
        """旧配置里遗留的 size 也要兑现，而不是像以前那样当作不存在。"""
        self.assertEqual(FontManager._resolve_multiplier("body", {"size": 21}, 14), 1.5)

    def test_multiplier_is_clamped(self):
        """倍率收进 0.5–3.0：更低读不清，更高会撑爆表格列宽。"""
        self.assertEqual(
            FontManager._resolve_multiplier("title", {"multiplier": 99}, 14), 3.0
        )
        self.assertEqual(
            FontManager._resolve_multiplier("title", {"multiplier": 0.01}, 14), 0.5
        )

    def test_qss_has_no_fixed_font_size(self):
        """QSS 里的字号必须全部随基准变化。

        取两个相邻基准，输出的字号集合不能有交集；有交集就说明某处
        写死了 px，改默认字号时它不会动。
        """

        def sizes(base):
            return set(re.findall(r"font-size:\s*(\d+)px", theme.build_qss(base)))

        fixed = sizes(14) & sizes(15)
        self.assertEqual(fixed, set(), f"QSS 中存在不随默认字号变化的字号: {fixed}")

    def test_no_hardcoded_font_size_in_gui(self):
        """GUI 源码里不许再出现 `font-size: Npx` 字面量。

        那种写法脱离配置。要字号请用 theme.font_px(role)。
        """
        offenders = list(_scan(HARDCODED_PX))
        self.assertEqual(offenders, [], "存在硬编码字号: " + ", ".join(offenders))

    def test_font_px_is_interpolated(self):
        """font_px(...) 必须包在 f-string 的 {} 里。

        裸写 `font-size: font_px('small')px` 是无效 CSS，Qt 会静默忽略整条
        声明（不报错、不警告），肉眼只能看出"字号没生效"。踩过一次。
        """
        offenders = _scan(BARE_CALL)
        self.assertEqual(offenders, [], "缺 {} 插值: " + ", ".join(offenders))


if __name__ == "__main__":
    unittest.main()
