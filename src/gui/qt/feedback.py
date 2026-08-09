"""反馈机制（P4）：InfoBar 提示与保存状态显示。

InfoBar 使用 qfluentwidgets 局部组件（成功/警告/失败），保存状态由
ProjectSaveBridge 发出信号、MainWindow 的 QStatusBar 呈现。
"""
from datetime import datetime

from ...logger import logger


def show_toast(widget, text: str, level: str = "success",
               duration: int = 3000) -> None:
    """在 widget 的顶层窗口右上角弹出 InfoBar 提示。失败时静默降级。"""
    try:
        from qfluentwidgets import InfoBar, InfoBarPosition
        window = widget.window()
        if level == "error":
            InfoBar.error("", text, parent=window,
                          position=InfoBarPosition.TOP_RIGHT, duration=duration)
        elif level == "warning":
            InfoBar.warning("", text, parent=window,
                            position=InfoBarPosition.TOP_RIGHT, duration=duration)
        else:
            InfoBar.success("", text, parent=window,
                            position=InfoBarPosition.TOP_RIGHT, duration=duration)
    except Exception as exc:  # pragma: no cover - 反馈失败不影响主流程
        logger.warning("[toast] InfoBar 显示失败: %s", exc)


def now_stamp() -> str:
    return datetime.now().strftime("%H:%M:%S")


SAVE_STATE_TEXTS = {
    "saving": "⏳ 正在自动保存中…",
    "saved": "✓ 所有修改已于 {stamp} 成功自动保存",
    "failed": "⚠ 保存失败，请检查文件权限或重试",
}


def save_state_message(state: str, stamp: str = "") -> str:
    template = SAVE_STATE_TEXTS.get(state, "")
    if not template:
        return ""
    return template.format(stamp=stamp)
