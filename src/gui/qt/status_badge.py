"""可勾选的项目完成状态控件。"""

from PySide6.QtCore import Qt
from PySide6.QtGui import QFont
from PySide6.QtWidgets import QCheckBox

from ...project_status import ProjectStatus
from ..font_manager import font_manager
from ..theme import TEXT_PRIMARY


class QtStatusBadge(QCheckBox):
    """用明确的复选框表达项目是否完成。

    勾选表示“项目已完成”，未勾选表示项目仍在编辑。状态更新时会暂时
    阻断信号，避免加载项目或保存回写时误触发用户操作回调。
    """

    def __init__(self, parent=None, status=None, **_kwargs):
        super().__init__("项目已完成", parent)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setToolTip("勾选后项目将标记为已完成；取消勾选可继续编辑")
        self.setStyleSheet(
            f"QCheckBox {{ color: {TEXT_PRIMARY}; background: transparent; spacing: 7px; }}"
        )
        self.set_status(status)
        self._apply_fonts()

    def configure_status(self, status: ProjectStatus | None) -> None:
        self.set_status(status)

    def set_status(self, status: ProjectStatus | None) -> None:
        previous = self.blockSignals(True)
        try:
            self.setChecked(status == ProjectStatus.DONE)
        finally:
            self.blockSignals(previous)

    def set_bg(self, _color: str) -> None:
        """保留旧接口；复选框不再使用状态色块。"""

    def set_pill(self, _background: str) -> None:
        """保留旧接口；复选框不再使用胶囊背景。"""

    def _apply_fonts(self) -> None:
        body = font_manager.get("body")
        if isinstance(body, QFont):
            self.setFont(body)
