"""新手引导：步骤定义、落点解析、完成状态语义。

刻意不建 MainWindow —— 用假的 window/content 喂给落点解析即可，
既快又不依赖图标字体环境（本机 qtawesome 加载 fa5r 会失败，
任何实例化真实窗口的测试都会被它带崩）。

最重要的一条回归：**引导启动失败时绝不能标记完成**。旧版把
``from qfluentwidgets import ... TailPosition``（真名 TeachingTipTailPosition）
写错，每次启动都在 except 里吞掉 ImportError，然后照样写下
``onboarding_done = True`` —— 结果引导一次都没出现过、也永远不会再试。
"""
import os
import tempfile
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

_TMP = tempfile.mkdtemp(prefix="cpa_onboarding_")
os.environ["CPA_CONFIG_DIR"] = _TMP
os.environ["CPA_PROJECTS_DIR"] = _TMP
os.environ["CPA_BACKUPS_DIR"] = _TMP
os.environ["CPA_LOG_DIR"] = _TMP

from PySide6.QtCore import Qt  # noqa: E402
from PySide6.QtWidgets import QApplication, QLabel, QPushButton, QWidget  # noqa: E402

import src.config_loader as config_loader  # noqa: E402
from src.gui.qt import onboarding as ob  # noqa: E402

_APP = None


def setUpModule() -> None:
    global _APP
    _APP = QApplication.instance() or QApplication([])


class _FakeContent:
    """够用的 content 替身：普通控件 + 两个字典型锚点。"""

    def __init__(self):
        self._bill_add_btn = QPushButton("记一笔")
        self._bills_table = QLabel("table")
        self._mode_buttons = {"simple": QPushButton("极简"), "audit": QPushButton("查账")}
        self._tab_buttons = {"bills": QPushButton("账单"), "workers": QPushButton("工种")}
        # 字典里混一个非控件值，确认解析时会被跳过
        self._mixed = {"bad": "not-a-widget", "good": QPushButton("好")}


class _FakeWindow:
    def __init__(self):
        self.sidebar = type("S", (), {"list_widget": QLabel("list")})()
        self._bar = QLabel("status")

    def statusBar(self):
        return self._bar


def _step(target: str, key=None) -> ob.GuideStep:
    return ob.GuideStep("t", "c", target, key=key)


class GuideStepDefinitionTests(unittest.TestCase):
    def test_every_step_is_fully_specified(self):
        self.assertGreaterEqual(len(ob.STEPS), 3)
        for step in ob.STEPS:
            with self.subTest(target=step.target):
                self.assertTrue(step.title)
                self.assertTrue(step.content)
                self.assertTrue(step.target)

    def test_dict_anchors_declare_which_entry_to_use(self):
        # _mode_buttons / _tab_buttons 是字典；不写 key 就只能"碰运气取第一个"，
        # 气泡会指到「账单管理」而不是「工作类型设置」。这里钉死这个约定。
        for step in ob.STEPS:
            leaf = step.target.rsplit(".", 1)[-1]
            if leaf in ("_mode_buttons", "_tab_buttons"):
                with self.subTest(target=step.target):
                    self.assertIsNotNone(step.key)

    def test_step_titles_are_unique(self):
        titles = [s.title for s in ob.STEPS]

        self.assertEqual(len(titles), len(set(titles)))

    def test_tail_positions_are_known(self):
        for step in ob.STEPS:
            with self.subTest(target=step.target):
                self.assertIn(step.tail, ("top", "bottom", "left", "right"))


class TargetResolutionTests(unittest.TestCase):
    def setUp(self):
        self.window = _FakeWindow()
        self.content = _FakeContent()

    def test_resolves_nested_widget(self):
        got = ob._resolve_target(self.window, self.content, "content._bill_add_btn")

        self.assertIs(got, self.content._bill_add_btn)

    def test_resolves_via_sidebar_attribute(self):
        got = ob._resolve_target(self.window, self.content, "sidebar.list_widget")

        self.assertIs(got, self.window.sidebar.list_widget)

    def test_calls_zero_arg_method_such_as_status_bar(self):
        got = ob._resolve_target(self.window, self.content, "window.statusBar")

        self.assertIs(got, self.window._bar)

    def test_unknown_path_returns_none(self):
        self.assertIsNone(ob._resolve_target(self.window, self.content, "content.没有这个"))
        self.assertIsNone(ob._resolve_target(self.window, self.content, "别的前缀.x"))

    def test_dict_anchor_is_preserved_not_flattened_to_none(self):
        # 曾经这里直接把非 QWidget 一律转成 None，导致字典型落点永远解析不到。
        got = ob._resolve_target(self.window, self.content, "content._mode_buttons")

        self.assertIsInstance(got, dict)

    def test_key_picks_the_intended_entry(self):
        got = ob._step_target(self.window, self.content, _step("content._tab_buttons", "workers"))

        self.assertIs(got, self.content._tab_buttons["workers"])

    def test_missing_key_falls_back_to_first_widget(self):
        got = ob._step_target(self.window, self.content, _step("content._mode_buttons"))

        self.assertIn(got, self.content._mode_buttons.values())

    def test_non_widget_dict_values_are_skipped(self):
        got = ob._step_target(self.window, self.content, _step("content._mixed"))

        self.assertIs(got, self.content._mixed["good"])

    def test_dict_without_widgets_resolves_to_none(self):
        self.content._empty = {"a": 1, "b": "x"}

        self.assertIsNone(ob._step_target(self.window, self.content, _step("content._empty")))

    def test_non_widget_result_is_rejected(self):
        self.content._version = "1.0.1"

        self.assertIsNone(ob._step_target(self.window, self.content, _step("content._version")))

    def test_real_step_targets_all_resolve(self):
        # 六步的锚点路径必须与真实 content/sidebar 的属性名对得上
        content = _FakeContent()
        content._bills_table = QLabel()
        window = _FakeWindow()
        for step in ob.STEPS:
            with self.subTest(target=step.target):
                self.assertIsNotNone(ob._step_target(window, content, step))


class OnboardingStateTests(unittest.TestCase):
    def setUp(self):
        config_loader._app_cache = None
        ob.reset_onboarding()

    def tearDown(self):
        config_loader._app_cache = None

    def test_reset_clears_the_marker(self):
        ob.mark_onboarding_done()

        ob.reset_onboarding()

        self.assertFalse(ob.is_onboarding_done())

    def test_mark_is_idempotent(self):
        ob.mark_onboarding_done()
        ob.mark_onboarding_done()

        self.assertTrue(ob.is_onboarding_done())

    def test_failure_to_show_the_card_does_not_mark_done(self):
        # 核心回归：展示失败却写标记，用户就永远看不到引导了。
        class _Boom(ob.WelcomeDialog):
            def exec(self):
                raise RuntimeError("模拟欢迎卡片构造失败")

        original = ob.WelcomeDialog
        ob.WelcomeDialog = _Boom
        try:
            ob.maybe_show_onboarding(None, None)
        finally:
            ob.WelcomeDialog = original

        self.assertFalse(ob.is_onboarding_done())

    def test_skipping_the_card_marks_done(self):
        class _Skip(ob.WelcomeDialog):
            def exec(self):
                return False

        original = ob.WelcomeDialog
        ob.WelcomeDialog = _Skip
        try:
            ob.maybe_show_onboarding(None, None)
        finally:
            ob.WelcomeDialog = original

        self.assertTrue(ob.is_onboarding_done())

    def test_already_done_short_circuits_without_showing_anything(self):
        ob.mark_onboarding_done()
        calls = []

        class _Counting(ob.WelcomeDialog):
            def exec(self):
                calls.append(1)
                return False

        original = ob.WelcomeDialog
        ob.WelcomeDialog = _Counting
        try:
            ob.maybe_show_onboarding(None, None)
        finally:
            ob.WelcomeDialog = original

        self.assertEqual(calls, [])

    def test_force_ignores_the_marker(self):
        ob.mark_onboarding_done()
        calls = []

        class _Counting(ob.WelcomeDialog):
            def exec(self):
                calls.append(1)
                return False

        original = ob.WelcomeDialog
        ob.WelcomeDialog = _Counting
        try:
            ob.maybe_show_onboarding(None, None, force=True)
        finally:
            ob.WelcomeDialog = original

        self.assertEqual(len(calls), 1)

    def test_accepting_the_card_with_no_usable_steps_still_marks_done(self):
        # 卡片点了「开始了解」，但窗口里没有任何可用落点（空项目、控件还没建）：
        # runner 必须一路跳完并收尾，不能卡住也不能永远重来。
        # window 必须是真的 QWidget —— 卡片以它作 parent 构造。
        class _Accept(ob.WelcomeDialog):
            def exec(self):
                return True

        class _EmptyContent:
            pass

        class _EmptyWindow(QWidget):
            sidebar = None

        original_card = ob.WelcomeDialog
        ob.WelcomeDialog = _Accept
        try:
            ob.maybe_show_onboarding(_EmptyWindow(), _EmptyContent())
        finally:
            ob.WelcomeDialog = original_card

        self.assertTrue(ob.is_onboarding_done())


class GuideRunnerTests(unittest.TestCase):
    """runner 的收尾语义：任何路径都必须塌缩到 finish()。"""

    def setUp(self):
        config_loader._app_cache = None
        ob.reset_onboarding()
        self.runner = ob._GuideRunner(_FakeWindow(), _FakeContent())

    def tearDown(self):
        config_loader._app_cache = None

    def test_finish_closes_the_tip_and_marks_done(self):
        self.runner._tip = None

        self.runner.finish()

        self.assertIsNone(self.runner._tip)
        self.assertTrue(ob.is_onboarding_done())

    def test_finish_is_safe_when_nothing_was_shown(self):
        self.runner.finish()
        self.runner.finish()

        self.assertTrue(ob.is_onboarding_done())

    def test_advancing_past_the_last_step_finishes(self):
        self.runner._index = len(ob.STEPS)

        self.runner._advance()

        self.assertTrue(ob.is_onboarding_done())


class AboutPanelReplayTests(unittest.TestCase):
    """关于面板的「重新查看新手引导」入口。"""

    def _make_chain(self, with_main: bool):
        """构造 设置面板 → 设置对话框 → 主窗口 的 Qt parent 链。

        主窗口用真 QWidget 加鸭子属性（content / sidebar），
        跟 AboutPanel._find_main_window 的判定方式一致，不建真 MainWindow。
        """
        from src.gui.qt.dialogs.settings.about_panel import AboutPanel

        main = QWidget() if with_main else None
        if with_main:
            main.content = QWidget()
            main.sidebar = QWidget()
        dialog = QWidget() if with_main else None
        if with_main:
            dialog.setParent(main)
            dialog.setWindowFlags(Qt.Window)
        panel = AboutPanel()
        if with_main:
            panel.setParent(dialog)
        return panel, dialog, main

    def test_find_main_window_walks_parent_chain(self):
        panel, dialog, main = self._make_chain(with_main=True)

        self.assertIs(panel._find_main_window(), main)
        panel.deleteLater()
        dialog.deleteLater()
        main.deleteLater()

    def test_find_main_window_returns_none_without_ancestors(self):
        panel, _dialog, _main = self._make_chain(with_main=False)

        self.assertIsNone(panel._find_main_window())
        panel.deleteLater()

    def test_replay_closes_settings_and_forces_guide(self):
        panel, dialog, main = self._make_chain(with_main=True)
        dialog.closeEvent = lambda event: setattr(dialog, "_closed", True) or event.accept()

        calls = []

        def _fake_show(window, content, force=False):
            calls.append((window, content, force))

        original = ob.maybe_show_onboarding
        ob.maybe_show_onboarding = _fake_show
        try:
            panel._replay_onboarding()
        finally:
            ob.maybe_show_onboarding = original

        self.assertEqual(calls, [(main, main.content, True)])
        panel.deleteLater()
        dialog.deleteLater()
        main.deleteLater()

    def test_replay_without_main_window_warns_instead_of_crashing(self):
        from src.gui.qt.dialogs.settings import about_panel as ap

        panel, _dialog, _main = self._make_chain(with_main=False)

        warnings = []
        original_qmb = ap.QMessageBox
        ap.QMessageBox = type(
            "QMB", (), {"warning": staticmethod(lambda *a, **k: warnings.append(a))}
        )
        try:
            panel._replay_onboarding()  # 不应抛异常
        finally:
            ap.QMessageBox = original_qmb

        self.assertEqual(len(warnings), 1)
        panel.deleteLater()


if __name__ == "__main__":
    unittest.main()
