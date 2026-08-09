"""通用确认对话框（Qt）。

优先使用 qfluentwidgets.MessageBox（毛玻璃遮罩 + Fluent 样式）；
构造失败（如 parent 缺失）时回退到标准 QMessageBox.Yes/No。
"""
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QDialog, QMessageBox

from ....logger import logger

_YES_TEXT = "确认"
_NO_TEXT = "取消"


def confirm_dialog(parent, title: str, message: str, default_yes: bool = False) -> bool:
    """弹出确认框，返回用户是否确认。

    default_yes=True 时默认焦点在「确认」按钮（替换/覆盖类操作）；
    False 时默认焦点在「取消」按钮。删除类操作的说明由调用方写入 message。
    """
    try:
        from qfluentwidgets import MessageBox

        if parent is None:
            raise ValueError("qfluentwidgets.MessageBox 需要非空 parent")
        box = MessageBox(title, message, parent)
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
