"""设置面板必须都能构建出来。

背景（2026-09-18）：统一字号时 `base.py` 的 `color_row` 改用了
`label_col_width()` 却忘了导入。面板初始化抛 NameError，被 SettingsDialog
捕获成「此设置页暂时无法加载」——compileall 通过、全量测试全绿，只有真实
渲染截图才看得出来。这个文件把「面板构建」本身钉住。

用户数据安全：CPA_CONFIG_DIR 指向临时目录（同 test_onboarding 的做法），
避免 SettingsDialog 关闭时把面板值写回真实 user_config.json。
"""
import os
import tempfile
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
_TMP = tempfile.mkdtemp(prefix="cpa_settings_panels_")
os.environ["CPA_CONFIG_DIR"] = _TMP
os.environ["CPA_LOG_DIR"] = _TMP

from PySide6.QtWidgets import QApplication  # noqa: E402

_APP = QApplication.instance() or QApplication([])


class SettingsPanelBuildTests(unittest.TestCase):
    def setUp(self):
        from src.gui.font_manager import font_manager
        font_manager.init_qt()

    def test_every_panel_builds_and_loads(self):
        """逐个面板单独构建 + load，报出具体异常而不是被对话框吞掉。"""
        from src.gui.qt.dialogs.settings import _PANELS

        failures = []
        for key, label, panel_cls in _PANELS:
            try:
                panel = panel_cls()
            except Exception as exc:
                failures.append("%s(%s) 构建失败: %s: %s"
                                % (key, label, type(exc).__name__, exc))
                continue
            try:
                panel.load()
            except NotImplementedError:
                pass
            except Exception as exc:
                failures.append("%s(%s) load 失败: %s: %s"
                                % (key, label, type(exc).__name__, exc))
            finally:
                panel.deleteLater()

        self.assertEqual(failures, [], " | ".join(failures))

    def test_settings_dialog_switches_every_page(self):
        """真的切一遍导航。

        面板构建在对话框里是被 try 包住降级成提示文案的，只测单类构造
        还漏得掉切换路径上的问题。
        """
        from PySide6.QtWidgets import QWidget

        from src.gui.qt.dialogs.settings import SettingsDialog, _PANELS

        # parent 必须在 Python 侧留引用：临时 QWidget 被 GC 时 shiboken 会连
        # 带回收 C++ 对象，对话框跟着没了（会报 "already deleted"）。
        parent = QWidget()
        dialog = SettingsDialog(parent)
        try:
            for row in range(len(_PANELS)):
                dialog._nav.setCurrentRow(row)
                _APP.processEvents()
            self.assertEqual(dialog._nav.count(), len(_PANELS))
        finally:
            dialog.close()
            dialog.deleteLater()
            parent.deleteLater()
            _APP.processEvents()


if __name__ == "__main__":
    unittest.main()
