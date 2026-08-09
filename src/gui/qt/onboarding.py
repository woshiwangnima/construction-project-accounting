"""新手引导（P4）：可关闭底部提示条 + 首次使用三步 TeachingTip。

- 底部提示条：启动后常驻内容区底部，可关闭；关闭后不再显示（user_config）。
- TeachingTip：首次启动依次指向「记一笔」→「双击编辑」→「右键更多」，
  可跳过（点外部即关闭），完成或跳过后不再重复（app_config）。
"""
from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QPushButton

from ...logger import logger
from ...config_loader import load_app, load_user, save_app, save_user
from ..font_manager import font_manager
from ..theme import SEGMENT_BG, TEXT_SECONDARY

ONBOARDING_KEY = "onboarding_done"
TIP_DISMISSED_KEY = "tip_dismissed"


def _is_onboarding_done() -> bool:
    try:
        return bool(load_app().get(ONBOARDING_KEY, False))
    except Exception:
        return False


def _mark_onboarding_done() -> None:
    try:
        cfg = load_app()
        if not cfg.get(ONBOARDING_KEY):
            cfg[ONBOARDING_KEY] = True
            save_app(cfg)
    except Exception as exc:
        logger.warning("[onboarding] 标记完成失败: %s", exc)


def _is_tip_dismissed() -> bool:
    try:
        return bool(load_user().get(TIP_DISMISSED_KEY, False))
    except Exception:
        return False


def _mark_tip_dismissed() -> None:
    try:
        cfg = load_user()
        cfg[TIP_DISMISSED_KEY] = True
        save_user(cfg)
    except Exception as exc:
        logger.warning("[onboarding] 提示条关闭状态保存失败: %s", exc)


class TipBar(QFrame):
    """内容区底部提示条：浅灰底圆角，可关闭且不再显示。"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setStyleSheet(
            f"background: {SEGMENT_BG}; border: none; border-radius: 8px;"
        )
        layout = QHBoxLayout(self)
        layout.setContentsMargins(14, 4, 8, 4)
        layout.setSpacing(8)
        self._lbl = QLabel("💡 **使用贴士**：点击右上角「+ 记一笔新账」录入数据 · 双击表格任意行可修改 · 所有数据实时自动保存")
        self._lbl.setStyleSheet(f"color: {TEXT_SECONDARY}; font-size: 13px; font-weight: bold;")
        layout.addWidget(self._lbl, 1)
        close_btn = QPushButton("\u2715")
        close_btn.setProperty("flat", True)
        close_btn.setFixedSize(24, 24)
        close_btn.clicked.connect(self.dismiss)
        layout.addWidget(close_btn)
        self.setVisible(False)

    def show_once(self) -> None:
        if not _is_tip_dismissed():
            self.setVisible(True)

    def dismiss(self) -> None:
        _mark_tip_dismissed()
        self.setVisible(False)


def maybe_show_onboarding(window, content) -> None:
    """首次启动三步引导：记一笔 → 双击编辑 → 右键更多。可跳过不重复。"""
    if _is_onboarding_done():
        return
    try:
        from qfluentwidgets import TeachingTip, TeachingTipView, TailPosition
        if not hasattr(content, "_bill_add_btn") or not hasattr(content, "_bills_table"):
            return

        def _step3() -> None:
            try:
                TeachingTip.make(
                    content._bills_table, "右键更多功能",
                    "在表格上点右键，可以复制、粘贴、审核、调整列显示。",
                    TailPosition.TOP, 4000, window,
                )
            except Exception:
                pass
            _mark_onboarding_done()

        def _step2() -> None:
            try:
                TeachingTip.make(
                    content._bills_table, "双击编辑记录",
                    "双击任意一行，可以修改这条记录的内容。",
                    TailPosition.TOP, 4000, window,
                )
            except Exception:
                pass
            QTimer.singleShot(4500, _step3)

        def _step1() -> None:
            try:
                TeachingTip.make(
                    content._bill_add_btn, "从这里开始记账",
                    "点击「记一笔」，选择工作项目和数量，金额会自动算好。",
                    TailPosition.BOTTOM, 4000, window,
                )
            except Exception:
                pass
            QTimer.singleShot(4500, _step2)

        QTimer.singleShot(2500, _step1)
    except Exception as exc:  # pragma: no cover - 引导失败不影响主流程
        logger.warning("[onboarding] 三步引导启动失败: %s", exc)
        _mark_onboarding_done()
