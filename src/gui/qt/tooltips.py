"""统一的高对比度说明 Tooltip。

原生 QToolTip 的前景色与背景色可能分别被 Windows、Qt 样式和局部 QSS
接管。这里改用 qfluentwidgets 的独立浮层，并在浮层自身设置完整配色，避免
依赖平台调色板继承顺序。
"""

from PySide6.QtWidgets import QWidget
from qfluentwidgets import ToolTip, ToolTipFilter, ToolTipPosition

from ..theme import BORDER_STRONG, RADIUS_SM, TOOLTIP_BG, TOOLTIP_FG


class ReadableToolTipFilter(ToolTipFilter):
    """创建自带完整前景/背景样式的 Tooltip，并拦截原生提示。"""

    def __init__(
        self, parent: QWidget, show_delay=300, position=ToolTipPosition.BOTTOM
    ):
        super().__init__(parent, show_delay, position)
        self._widget = parent

    def _createToolTip(self):
        tip = ToolTip(self._widget.toolTip(), self._widget.window())
        tip.container.setStyleSheet(
            f"QFrame#container {{ background: {TOOLTIP_BG};"
            f" border: 1px solid {BORDER_STRONG}; border-radius: {RADIUS_SM}px; }}"
        )
        tip.label.setStyleSheet(
            f"QLabel#contentLabel {{ color: {TOOLTIP_FG};"
            " background: transparent; border: none; }"
        )
        return tip


def set_readable_tooltip(
    widget: QWidget,
    text: str,
    *,
    position=ToolTipPosition.BOTTOM,
    delay: int = 300,
) -> ReadableToolTipFilter:
    """设置统一说明文字，并保留过滤器引用直到控件销毁。"""
    widget.setToolTip(text)
    existing = widget.findChild(ReadableToolTipFilter, "cpaReadableToolTipFilter")
    if existing is not None:
        return existing
    tooltip_filter = ReadableToolTipFilter(widget, delay, position)
    tooltip_filter.setObjectName("cpaReadableToolTipFilter")
    widget.installEventFilter(tooltip_filter)
    return tooltip_filter
