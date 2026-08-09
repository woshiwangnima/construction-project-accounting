"""快捷键设置面板：查看与修改全局快捷键（写入 user_config shortcut_settings）。"""
from PySide6.QtCore import Qt
from PySide6.QtGui import QKeySequence, QKeyEvent
from PySide6.QtWidgets import (
    QDialog, QFrame, QHBoxLayout, QLabel, QPushButton, QVBoxLayout,
)

from ....shortcut_manager import (
    shortcut_manager, DEFAULT_SHORTCUTS, ACTION_GROUPS,
)
from ....theme import BORDER, TEXT_PRIMARY, TEXT_SECONDARY
from .base import BasePanel, separator

_ARROW_DISPLAY = {"Up": "↑", "Down": "↓", "Left": "←", "Right": "→"}


def _tk_event_and_accel(e: QKeyEvent):
    """把 QKeyEvent 翻译为 Tk 事件串与显示加速键文本。

    返回 (tk_event, accel_text)；纯修饰键按下返回 (None, None)。
    """
    mods: list[str] = []
    accel: list[str] = []
    if e.modifiers() & Qt.ControlModifier:
        mods.append("Control")
        accel.append("Ctrl")
    if e.modifiers() & Qt.ShiftModifier:
        mods.append("Shift")
        accel.append("Shift")
    if e.modifiers() & Qt.AltModifier:
        mods.append("Alt")
        accel.append("Alt")

    key = e.key()
    if key in (Qt.Key_Control, Qt.Key_Shift, Qt.Key_Alt, Qt.Key_Meta,
               Qt.Key_AltGr, Qt.Key_unknown):
        return None, None

    text = QKeySequence(key).toString()
    if not text:
        return None, None

    tk_key = text
    display = text
    if len(text) == 1 and text.isalpha():
        tk_key = text.lower()
    display = _ARROW_DISPLAY.get(text, display)
    if text == "Return":
        display = "Enter"
    elif text == "Delete":
        display = "Del"

    if mods:
        tk_event = "<" + "-".join(mods + [tk_key]) + ">"
    else:
        tk_event = "<" + tk_key + ">"
    accel_text = "+".join(accel + [display])
    return tk_event, accel_text


class RecordKeyDialog(QDialog):
    """按键录制对话框：用户按下新组合后立即保存并关闭。"""

    def __init__(self, parent, action_id: str, on_recorded):
        super().__init__(parent)
        self._action_id = action_id
        self._on_recorded = on_recorded
        self.setWindowTitle("设置快捷键")
        self.setModal(True)
        self.setFixedSize(360, 130)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 16, 20, 16)
        layout.setSpacing(10)

        title = QLabel(f"为「{shortcut_manager.get_label(action_id)}」设置新快捷键")
        title.setWordWrap(True)
        layout.addWidget(title)

        hint = QLabel("请按下新的快捷键组合…（按 Esc 取消）")
        hint.setStyleSheet(f"color: {TEXT_SECONDARY};")
        layout.addWidget(hint)
        layout.addStretch(1)

    def keyPressEvent(self, event: QKeyEvent) -> None:
        if event.key() == Qt.Key_Escape:
            self.reject()
            return
        tk_event, accel_text = _tk_event_and_accel(event)
        if tk_event is None:
            return
        self._on_recorded(self._action_id, tk_event, accel_text)
        self.accept()


class ClickableRow(QFrame):
    """点击行任意位置触发回调（用于快捷键行的按键录制入口）。"""

    def __init__(self, on_click, parent=None):
        super().__init__(parent)
        self._on_click = on_click

    def mousePressEvent(self, event) -> None:
        self._on_click()
        super().mousePressEvent(event)


class ShortcutPanel(BasePanel):
    def title_text(self) -> str:
        return "⌨ 快捷键设置"

    def hint_text(self) -> str:
        return "修改后立即保存并生效；点击行或「重新绑定」后按下新组合即可。"

    def build(self, layout: QVBoxLayout) -> None:
        self._accel_labels: dict[str, QLabel] = {}

        for group_name, action_ids in ACTION_GROUPS:
            layout.addWidget(separator())
            group = QLabel(group_name)
            group.setStyleSheet("font-size: 14px; font-weight: bold;")
            layout.addWidget(group)
            for action_id in action_ids:
                if action_id not in DEFAULT_SHORTCUTS:
                    continue
                self._build_action_row(layout, action_id)

        layout.addWidget(separator())
        layout.addWidget(separator())
        btn_row = QHBoxLayout()
        reset_btn = QPushButton("恢复默认")
        reset_btn.setProperty("secondary", True)
        reset_btn.clicked.connect(self._on_reset)
        btn_row.addWidget(reset_btn)
        btn_row.addStretch(1)
        layout.addLayout(btn_row)
        layout.addStretch(1)

    def _build_action_row(self, layout: QVBoxLayout, action_id: str) -> None:
        defaults = DEFAULT_SHORTCUTS[action_id]

        row = ClickableRow(lambda: self._rebind(action_id))
        row.setStyleSheet(
            f"background: transparent; border: 1px solid {BORDER};"
            " border-radius: 8px;"
        )
        row.setCursor(Qt.PointingHandCursor)
        row_layout = QHBoxLayout(row)
        row_layout.setContentsMargins(10, 6, 10, 6)
        row_layout.setSpacing(8)

        name = QLabel(defaults["label"])
        name.setStyleSheet(f"color: {TEXT_SECONDARY};")
        row_layout.addWidget(name, 1)

        accel = QLabel(defaults["accel"])
        accel.setStyleSheet(
            "background: #f2f2f7; border-radius: 6px; padding: 3px 10px;"
            f"color: {TEXT_PRIMARY}; font-weight: bold;"
        )
        row_layout.addWidget(accel)
        self._accel_labels[action_id] = accel

        rebind_btn = QPushButton("重新绑定")
        rebind_btn.setProperty("flat", True)
        rebind_btn.clicked.connect(lambda *_, a=action_id: self._rebind(a))
        row_layout.addWidget(rebind_btn)

        layout.addWidget(row)

    # ── 重绑定 ──────────────────────────────────────────────────────────

    def _rebind(self, action_id: str) -> None:
        dlg = RecordKeyDialog(self, action_id, self._on_recorded)
        dlg.exec()

    def _on_recorded(self, action_id: str, tk_event: str, accel_text: str) -> None:
        settings = shortcut_manager.get_all_settings()
        settings[action_id] = {
            "event": tk_event,
            "accel": accel_text,
            "label": DEFAULT_SHORTCUTS[action_id]["label"],
        }
        shortcut_manager.save_settings(settings)
        self._accel_labels[action_id].setText(accel_text)

    # ── 加载 / 保存 ────────────────────────────────────────────────────

    def load(self) -> None:
        settings = shortcut_manager.get_all_settings()
        for action_id, data in settings.items():
            label = self._accel_labels.get(action_id)
            if label is not None:
                label.setText(data.get("accel", ""))

    def save(self) -> None:
        # 修改在 _on_recorded() 中立即落盘，无需关闭时再次写入。
        pass

    def _on_reset(self) -> None:
        shortcut_manager.reset_all()
        self.load()
