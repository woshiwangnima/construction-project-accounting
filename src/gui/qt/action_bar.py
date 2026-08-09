"""选中行操作条（P3）：表格下方常显操作条，由选择状态驱动。

无选择 / 单选 / 多选 / 只读（已完成项目）四种状态自动切换按钮可用性，
功能与右键菜单一致（右键保留给熟手），新手无需发现右键即可操作。
"""
from qtawesome import icon as qta_icon
from PySide6.QtCore import QSize, Signal
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QPushButton

from ..font_manager import font_manager
from ..theme import CARD_BG, CARD_BORDER, DANGER_FG, TEXT_SECONDARY

BTN_TEXT = {
    "edit": "编辑",
    "up": "上移",
    "down": "下移",
    "copy": "复制",
    "paste": "粘贴",
    "delete": "删除",
}

BTN_ICON = {
    "edit": "fa5s.edit",
    "up": "fa5s.arrow-up",
    "down": "fa5s.arrow-down",
    "copy": "fa5s.copy",
    "paste": "fa5s.clipboard",
    "delete": "fa5s.trash-alt",
}


class ActionBar(QFrame):
    """账单表格下方的操作条。通过 set_rows() 驱动可用状态。"""

    edit_requested = Signal(int)        # 行号
    up_requested = Signal(int)
    down_requested = Signal(int)
    copy_requested = Signal(list)       # 行号列表
    paste_requested = Signal(list)
    delete_requested = Signal(int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._rows: list[int] = []
        self.setStyleSheet(
            f"background: {CARD_BG}; border: 1px solid {CARD_BORDER};"
            f"border-radius: 8px;"
        )
        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 4, 8, 4)
        layout.setSpacing(6)

        def _make(action: str, slot) -> QPushButton:
            btn = QPushButton(BTN_TEXT[action])
            btn.setProperty("secondary", True)
            btn.setIcon(qta_icon(BTN_ICON[action]))
            btn.setIconSize(QSize(16, 16))
            btn.clicked.connect(slot)
            layout.addWidget(btn)
            return btn

        self._btn_edit = _make("edit", lambda: self._emit_single(self.edit_requested))
        self._btn_up = _make("up", lambda: self._emit_single(self.up_requested))
        self._btn_down = _make("down", lambda: self._emit_single(self.down_requested))
        self._btn_copy = _make("copy", lambda: self.copy_requested.emit(list(self._rows)))
        self._btn_paste = _make("paste", lambda: self.paste_requested.emit(list(self._rows)))
        self._btn_delete = _make("delete", lambda: self._emit_single(self.delete_requested))
        self._btn_delete.setProperty("danger", True)

        layout.addStretch(1)
        self._count_lbl = QLabel("未选中")
        self._count_lbl.setStyleSheet(f"color: {TEXT_SECONDARY};")
        layout.addWidget(self._count_lbl)

    def _emit_single(self, signal) -> None:
        if self._rows:
            signal.emit(self._rows[0])

    def set_rows(self, rows: list[int], editable: bool) -> None:
        """按当前选中行集合 + 可编辑性刷新按钮状态。"""
        self._rows = sorted(set(rows))
        single = len(self._rows) == 1
        self._btn_edit.setEnabled(editable and single)
        self._btn_up.setEnabled(editable and single)
        self._btn_down.setEnabled(editable and single)
        self._btn_copy.setEnabled(len(self._rows) >= 1)
        self._btn_paste.setEnabled(editable)
        self._btn_delete.setEnabled(editable and single)
        self._count_lbl.setText(
            f"选中 {len(self._rows)} 行" if self._rows else "未选中"
        )

    def set_editable(self, editable: bool) -> None:
        self.set_rows(self._rows, editable)
