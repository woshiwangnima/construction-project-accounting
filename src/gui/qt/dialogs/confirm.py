"""通用确认对话框（Qt）。

优先使用 qfluentwidgets.MessageBox（毛玻璃遮罩 + Fluent 样式）；
构造失败（如 parent 缺失）时回退到标准 QMessageBox.Yes/No。
"""
from PySide6.QtCore import QPoint, Qt
from PySide6.QtWidgets import QDialog, QMessageBox

from ....logger import logger

_YES_TEXT = "确认"
_NO_TEXT = "取消"


def _resolve_parent(parent):
    """把父控件提升到顶层窗口。

    qfluentwidgets 的 MaskDialogBase 用
    ``setGeometry(0, 0, parent.width(), parent.height())`` 决定遮罩尺寸，
    再把对话框居中放进遮罩。传入窄的子控件（如项目侧边栏，约 400px）时，
    遮罩就只有那么宽，正文被迫提前折行、按钮被裁掉。
    """
    if parent is None:
        return None
    window = parent.window() if hasattr(parent, "window") else None
    return window if window is not None else parent


def _fit_to_parent(box, target) -> None:
    """让遮罩覆盖父窗口的实际屏幕区域。

    MaskDialogBase 用的是 ``setGeometry(0, 0, w, h)``，即屏幕坐标原点；
    窗口没有贴着屏幕左上角时遮罩会错位到别处。这里按父窗口的真实位置重设。
    """
    try:
        origin = target.mapToGlobal(QPoint(0, 0))
        box.setGeometry(origin.x(), origin.y(), target.width(), target.height())
    except Exception as exc:
        logger.debug("[confirm] 遮罩定位失败，沿用默认几何: %s", exc)


def confirm_dialog(parent, title: str, message: str, default_yes: bool = False) -> bool:
    """弹出确认框，返回用户是否确认。

    default_yes=True 时默认焦点在「确认」按钮（替换/覆盖类操作）；
    False 时默认焦点在「取消」按钮。删除类操作的说明由调用方写入 message。
    """
    target = _resolve_parent(parent)
    try:
        from qfluentwidgets import MessageBox

        if target is None:
            raise ValueError("qfluentwidgets.MessageBox 需要非空 parent")
        box = MessageBox(title, message, target)
        _fit_to_parent(box, target)
    except Exception as exc:
        logger.debug("[confirm] qfluentwidgets 不可用，回退 QMessageBox: %s", exc)
        result = QMessageBox.question(
            parent,
            title,
            message,
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.Yes if default_yes else QMessageBox.No,
        )
        return result == QMessageBox.Yes

    box.yesButton.setText(_YES_TEXT)
    box.cancelButton.setText(_NO_TEXT)
    # 构造时按钮无焦点；exec 显示后才会应用。用 NoFocusReason 提前设置，
    # 避免焦点抢占父窗口控件。
    target = box.yesButton if default_yes else box.cancelButton
    target.setFocus(Qt.NoFocusReason)
    try:
        accepted = box.exec() == QDialog.Accepted
    except Exception as exc:
        logger.warning("[confirm] 对话框执行失败，回退 QMessageBox: %s", exc)
        result = QMessageBox.question(
            parent,
            title,
            message,
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.Yes if default_yes else QMessageBox.No,
        )
        return result == QMessageBox.Yes
    return accepted
