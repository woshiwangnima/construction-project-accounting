"""Qt 状态徽章（替代 Tk StatusBadge / ClickableStatusBadge）。

横向 pill 布局：左侧状态圆点 + 右侧文字，浅色底 + 深色加粗字，
保证中年用户可读性。可点击版支持 on_click 回调。
"""
from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QHBoxLayout, QLabel, QWidget

from ...project_status import ProjectStatus
from ..font_manager import font_manager
from ..theme import (
    INFO_BG, STATUS_DONE_FG, STATUS_EDITING_FG, SUCCESS_BG,
)


class QtStatusBadge(QWidget):
    clicked = Signal()

    def __init__(self, parent=None, status=None, *, icon=None, text=None,
                 color=None):
        super().__init__(parent)
        self._status = status
        self._icon = icon
        self._text = text
        self._color = color

        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 4, 12, 4)
        layout.setSpacing(6)
        self._icon_lbl = QLabel()
        self._icon_lbl.setAlignment(Qt.AlignCenter)
        self._text_lbl = QLabel()
        self._text_lbl.setAlignment(Qt.AlignCenter)
        layout.addWidget(self._icon_lbl)
        layout.addWidget(self._text_lbl)
        self.configure_status(status)
        self._apply_fonts()

    def configure_status(self, status: ProjectStatus | None) -> None:
        self._status = status
        if status is None:
            self._icon_lbl.setText("")
            self._text_lbl.setText("")
            self.setStyleSheet("background: transparent;")
            return
        self._icon_lbl.setText(self._icon if self._icon is not None else status.icon)
        self._text_lbl.setText(self._text if self._text is not None else status.display_name)
        color = self._color if self._color is not None else status.color
        if status == ProjectStatus.EDITING:
            bg = INFO_BG
        elif status == ProjectStatus.DONE:
            bg = SUCCESS_BG
        else:
            bg = "transparent"
        self.setStyleSheet(
            f"background: {bg}; border: none; border-radius: 14px;"
            f" color: {color};"
        )
        self._icon_lbl.setStyleSheet(f"color: {color}; background: transparent;")
        self._text_lbl.setStyleSheet(f"color: {color}; background: transparent;")

    def set_status(self, status: ProjectStatus | None) -> None:
        self.configure_status(status)

    def set_bg(self, color: str) -> None:
        self.setStyleSheet(f"background: {color};")

    def set_pill(self, background: str) -> None:
        """pill 容器样式：圆角背景 + 内边距；未调用时保持透明（默认）。"""
        self.setStyleSheet(
            f"background: {background}; border-radius: 14px;"
        )

    def _apply_fonts(self) -> None:
        body_bold = font_manager.get("body_bold")
        self._icon_lbl.setFont(body_bold)
        self._text_lbl.setFont(body_bold)
