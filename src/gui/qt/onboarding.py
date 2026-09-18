"""新手引导：首启欢迎卡片 + 可跳过的分步高亮。

三条设计约束（都是踩过坑的）：

1. **不自动消失**。气泡的 ``duration`` 传负数，由用户点「下一步」推进。
   早期版本每步 4 秒自动关闭，还没看完就没了。
2. **随时可跳过**。欢迎卡片和每个气泡上都有跳过入口，跳过即写入
   ``onboarding_done``，不再自动弹出。
3. **引导失败不得标记完成**。旧版把 import 写错成 ``TailPosition``（真名
   ``TeachingTipTailPosition``），每次启动都在 except 里吞掉异常，然后照样写下
   ``onboarding_done = True`` —— 结果是引导一次都没出现过，而且永远不会再尝试。
   现在只有"真的展示过"才落标记。

想重看：设置 → 关于 → 「重新查看新手引导」（或调 ``reset_onboarding()``）。
"""
from dataclasses import dataclass

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QApplication, QDialog, QFrame, QHBoxLayout, QLabel, QPushButton,
    QVBoxLayout, QWidget,
)

from ...config_loader import load_app, load_user, save_app, save_user
from ...logger import logger
from ..theme import (ACCENT, BORDER, SEGMENT_BG, TEXT_PRIMARY, TEXT_SECONDARY, font_px)
from .dialogs.confirm import _fit_to_parent, _resolve_parent

ONBOARDING_KEY = "onboarding_done"
TIP_DISMISSED_KEY = "tip_dismissed"

# 欢迎卡片上的功能清单：(强调词, 一句话说明)
FEATURES = (
    ("记一笔账", "点右上角「记一笔新账」，选工作项目、填数量或公式，金额自动算好。"),
    ("改一条账", "双击任意一行即可修改；鼠标停在某行，行尾会出现上移 / 下移 / 删除。"),
    ("按需看列", "右上角切换「极简速览 / 查账模式 / 显示全部」，粗细程度随场景切换。"),
    ("维护工种", "「工作类型设置」里管理工种、单价与计费方式（按量或按项）。"),
    ("分项目管理", "左侧每份项目一份账，可新建、切换、导出；导入导出也在那里。"),
    ("自动保存", "所有改动实时落盘，底部状态栏会显示保存状态，不需要手动存盘。"),
)


@dataclass(frozen=True)
class GuideStep:
    """一步引导。``target`` 是控件路径，``tail`` 决定气泡尾巴朝向。"""

    title: str
    content: str
    target: str
    tail: str = "bottom"
    page: str | None = None
    key: str | None = None


# 只讲高频主流程（导入导出等低频功能留给用户真正需要时看）。
STEPS: tuple[GuideStep, ...] = (
    GuideStep(
        "从这里记账",
        "点「记一笔新账」，选好工作项目和数量，金额会自动算出来。",
        "content._bill_add_btn",
        tail="bottom",
        page="bills",
    ),
    GuideStep(
        "改账、调顺序",
        "双击一行改内容；把鼠标停到某一行，行尾会出现 ↑ ↓ ✕ 用来调序和删除。",
        "content._bills_table",
        tail="top",
        page="bills",
    ),
    GuideStep(
        "列的粗细随你调",
        "极简速览少看几列，查账模式留下对账要用的列，显示全部则一览无余。",
        "content._mode_buttons",
        tail="bottom",
        page="bills",
        key="simple",
    ),
    GuideStep(
        "工种和单价在这里维护",
        "切到「工作类型设置」，管理工种、单价，以及按量还是按项计费。",
        "content._tab_buttons",
        tail="top",
        page="bills",
        key="workers",
    ),
    GuideStep(
        "一份项目一份账",
        "左侧可以新建、切换、搜索项目；右键项目还有更多操作。",
        "sidebar.list_widget",
        tail="right",
    ),
    GuideStep(
        "不用手动保存",
        "所有改动实时自动保存，底部状态栏会告诉你保存结果。",
        "window.statusBar",
        tail="bottom",
    ),
)


# ── 完成状态 ──────────────────────────────────────────────────────────


def is_onboarding_done() -> bool:
    try:
        return bool(load_app().get(ONBOARDING_KEY, False))
    except Exception as exc:
        logger.warning("[onboarding] 读取完成状态失败: %s", exc)
        return False


def mark_onboarding_done() -> None:
    try:
        cfg = load_app()
        if not cfg.get(ONBOARDING_KEY):
            cfg[ONBOARDING_KEY] = True
            save_app(cfg)
    except Exception as exc:
        logger.warning("[onboarding] 标记完成失败: %s", exc)


def reset_onboarding() -> None:
    """清掉完成标记，下次启动（或立刻手动调用）会重新引导。"""
    try:
        cfg = load_app()
        cfg[ONBOARDING_KEY] = False
        save_app(cfg)
    except Exception as exc:
        logger.warning("[onboarding] 重置引导状态失败: %s", exc)


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


# ── 底部提示条 ────────────────────────────────────────────────────────


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
        self._lbl = QLabel("使用贴士：点击右上角「记一笔新账」录入数据 · 双击表格任意行可修改 · 所有数据实时自动保存")
        self._lbl.setStyleSheet(f"color: {TEXT_SECONDARY}; font-size: {font_px('small')}px; font-weight: bold;")
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


# ── 欢迎卡片 ──────────────────────────────────────────────────────────


def _feature_row(index: int, headline: str, detail: str) -> QWidget:
    """一条功能说明：序号 + 加粗标题 + 灰色说明，两行内讲完。"""
    row = QWidget()
    layout = QHBoxLayout(row)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.setSpacing(10)

    badge = QLabel(str(index))
    badge.setFixedSize(20, 20)
    badge.setAlignment(Qt.AlignCenter)
    badge.setStyleSheet(
        f"background: {ACCENT}; color: #ffffff; border-radius: 10px;"
        f" font-size: {font_px('small')}px; font-weight: bold;"
    )
    layout.addWidget(badge, 0, Qt.AlignTop)

    text = QLabel(
        f'<span style="color:{TEXT_PRIMARY}; font-weight:bold;">{headline}</span>'
        f'<span style="color:{TEXT_SECONDARY};">　{detail}</span>'
    )
    text.setWordWrap(True)
    text.setStyleSheet(f"font-size: {font_px('small')}px;")
    layout.addWidget(text, 1)
    return row


class WelcomeDialog(QWidget):
    """首次启动的欢迎卡片：列功能清单 + 「跳过引导」/「开始了解」。

    不用 qfluentwidgets 的 MessageBox：它的正文是定宽单栏文本，
    塞不下这种"标题 + 说明"的多行清单，宽度也会被文字撑得很窄。
    """

    #: 卡片最小宽度；太窄时说明文字会被拆得支离破碎。
    MIN_WIDTH = 520

    def __init__(self, parent=None):
        super().__init__(parent)

    def exec(self) -> bool:
        """返回用户是否选择「开始了解」。"""
        try:
            return self._exec_fluent()
        except Exception as exc:
            logger.warning("[onboarding] 欢迎卡片不可用，回退原生对话框: %s", exc)
            return self._exec_fallback()

    # ── 主路径：qfluentwidgets 样式 ──

    def _exec_fluent(self) -> bool:
        from qfluentwidgets import MessageBoxBase

        target = _resolve_parent(self.parent())
        if target is None:
            raise ValueError("欢迎卡片需要非空父窗口")

        min_width = self.MIN_WIDTH

        class _Welcome(MessageBoxBase):
            def __init__(self, parent):
                super().__init__(parent)
                self._build()
                # MessageBoxBase 已把 yesButton 接到 accept()，这里不再重复连接。

            def _build(self):
                title = QLabel("👋 欢迎使用 施工记账")
                title.setStyleSheet(
                    f"color: {TEXT_PRIMARY}; font-size: {font_px('heading')}px; font-weight: bold;"
                )
                self.viewLayout.addWidget(title)

                intro = QLabel("花 30 秒了解一下，能少走不少弯路。")
                intro.setStyleSheet(f"color: {TEXT_SECONDARY}; font-size: {font_px('small')}px;")
                self.viewLayout.addWidget(intro)

                line = QFrame()
                line.setFixedHeight(1)
                line.setStyleSheet(f"background: {BORDER};")
                self.viewLayout.addWidget(line)

                for i, (headline, detail) in enumerate(FEATURES, start=1):
                    self.viewLayout.addWidget(_feature_row(i, headline, detail))

                self.viewLayout.addSpacing(4)
                self.widget.setMinimumWidth(min_width)
                self.yesButton.setText("开始了解")
                self.cancelButton.setText("跳过引导")

        box = _Welcome(target)
        _fit_to_parent(box, target)
        return box.exec() == QDialog.Accepted

    # ── 兜底：原生 QMessageBox ──

    def _exec_fallback(self) -> bool:
        from PySide6.QtWidgets import QMessageBox

        lines = [f"{i}. {h}——{d}" for i, (h, d) in enumerate(FEATURES, start=1)]
        box = QMessageBox(self.parent())
        box.setWindowTitle("欢迎使用 施工记账")
        box.setText("花 30 秒了解一下，能少走不少弯路。")
        box.setInformativeText("\n\n".join(lines))
        yes = box.addButton("开始了解", QMessageBox.AcceptRole)
        box.addButton("跳过引导", QMessageBox.RejectRole)
        box.exec()
        return box.clickedButton() is yes


# ── 分步高亮 ──────────────────────────────────────────────────────────


def _resolve_target(window, content, path: str):
    """按 'content._bill_add_btn' / 'sidebar.list_widget' 这类路径取对象。

    返回的不一定是控件：``content._mode_buttons`` 这类是控件字典，
    由 ``_step_target`` 再决定取哪一项。
    """
    head, _, rest = path.partition(".")
    if head == "content":
        obj = content
    elif head == "window":
        obj = window
    elif head == "sidebar":
        obj = getattr(window, "sidebar", None)
    else:
        return None
    for name in (rest.split(".") if rest else ()):
        obj = getattr(obj, name, None)
        if obj is None:
            return None
    # window.statusBar 这类是无参方法，取到的结果才是目标
    if callable(obj) and not isinstance(obj, QWidget):
        try:
            obj = obj()
        except Exception:
            return None
    return obj


def _step_target(window, content, step: "GuideStep"):
    """定位该步的落点控件。

    字典型锚点（``content._mode_buttons`` / ``_tab_buttons``）按 ``step.key``
    取项；没指定 key 就退化成"第一个控件成员"。
    """
    obj = _resolve_target(window, content, step.target)
    if isinstance(obj, dict):
        if step.key is not None and isinstance(obj.get(step.key), QWidget):
            return obj[step.key]
        for value in obj.values():
            if isinstance(value, QWidget):
                return value
        return None
    return obj if isinstance(obj, QWidget) else None


class _GuideRunner:
    """按顺序播放引导气泡；任一步的落点缺失就跳过该步，不会中断整条链。"""

    def __init__(self, window, content):
        self.window = window
        self.content = content
        self._tip = None
        self._index = 0

    # ── 对外 ──

    def start(self) -> None:
        self._index = -1
        self._advance()

    def finish(self) -> None:
        """结束引导（看完或跳过），并标记不再自动弹出。"""
        self._close_tip()
        mark_onboarding_done()

    # ── 内部 ──

    def _close_tip(self) -> None:
        tip = self._tip
        self._tip = None
        if tip is not None:
            try:
                tip.close()
            except Exception as exc:
                logger.debug("[onboarding] 关闭气泡失败: %s", exc)

    def _advance(self) -> None:
        self._close_tip()
        self._index += 1
        while self._index < len(STEPS):
            step = STEPS[self._index]
            target = self._prepare(step)
            if target is not None:
                try:
                    self._show(step, target)
                except Exception as exc:
                    logger.warning("[onboarding] 第 %s 步展示失败，跳过: %s",
                                   self._index + 1, exc)
                    self._index += 1
                    continue
                return
            logger.debug("[onboarding] 第 %s 步落点不可用，跳过: %s",
                         self._index + 1, step.target)
            self._index += 1
        # 全部放完 → 结束
        self.finish()

    def _prepare(self, step: "GuideStep"):
        """切到该步所在页，返回可见的落点控件（不可用则返回 None）。"""
        if step.page:
            try:
                self.content._switch_tab(step.page)
                # 切页要等布局跑完，落点控件的 isVisible() 才可信。
                QApplication.processEvents()
            except Exception as exc:
                logger.debug("[onboarding] 切换页面失败: %s", exc)
        target = _step_target(self.window, self.content, step)
        if target is None or not target.isVisible():
            return None
        return target

    def _show(self, step: "GuideStep", target) -> None:
        from qfluentwidgets import (
            TeachingTip, TeachingTipTailPosition, TeachingTipView,
        )

        tails = {
            "top": TeachingTipTailPosition.TOP,
            "bottom": TeachingTipTailPosition.BOTTOM,
            "left": TeachingTipTailPosition.LEFT,
            "right": TeachingTipTailPosition.RIGHT,
        }
        tail = tails.get(step.tail, TeachingTipTailPosition.BOTTOM)
        total = len(STEPS)
        view = TeachingTipView(
            f"{step.title}　（{self._index + 1}/{total}）",
            step.content,
            isClosable=True,
            tailPosition=tail,
            parent=self.window,
        )
        view.addWidget(self._button_row(is_last=self._index == total - 1),
                       0, Qt.AlignRight)
        # duration < 0：不自动消失，由用户点「下一步」推进。
        self._tip = TeachingTip.make(view, target, -1, tail, self.window)

    def _button_row(self, is_last: bool) -> QWidget:
        row = QWidget()
        layout = QHBoxLayout(row)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        skip = QPushButton("跳过引导")
        skip.setProperty("flat", True)
        skip.setCursor(Qt.PointingHandCursor)
        skip.setStyleSheet(
            f"QPushButton {{ border: none; color: {TEXT_SECONDARY};"
            f" font-size: {font_px('small')}px; padding: 4px 6px; }}"
            f"QPushButton:hover {{ color: {ACCENT}; }}"
        )
        skip.clicked.connect(self.finish)
        layout.addWidget(skip)

        nxt = QPushButton("知道了" if is_last else "下一步")
        nxt.setCursor(Qt.PointingHandCursor)
        nxt.setStyleSheet(
            f"QPushButton {{ background: {ACCENT}; color: #ffffff; border: none;"
            f" border-radius: 6px; padding: 5px 14px; font-size: {font_px('small')}px;"
            " font-weight: bold; }"
        )
        nxt.clicked.connect(self._advance)
        layout.addWidget(nxt)
        return row


def run_guide(window, content) -> "_GuideRunner":
    """立刻播放分步引导（不检查完成标记）。"""
    runner = _GuideRunner(window, content)
    # 挂到窗口上，保证 runner 在整个引导期间存活（按钮回调依赖它）。
    window._onboarding_runner = runner
    runner.start()
    return runner


def maybe_show_onboarding(window, content, force: bool = False) -> None:
    """首次启动入口：欢迎卡片 → （用户选择）分步高亮。

    ``force=True`` 时忽略完成标记，用于设置里的「重新查看新手引导」。

    注意：只有卡片真的弹出来过才写 ``onboarding_done``。构造阶段就异常的话
    保留未完成状态，下次启动还会重试 —— 反过来（失败也算完成）会让引导
    永远消失，这正是旧版的行为。
    """
    if not force and is_onboarding_done():
        return
    try:
        started = WelcomeDialog(window).exec()
    except Exception as exc:  # pragma: no cover - 兜底，正常不会走到
        logger.warning("[onboarding] 欢迎卡片启动失败，保留未完成状态: %s", exc)
        return

    if started:
        run_guide(window, content)
    else:
        mark_onboarding_done()
