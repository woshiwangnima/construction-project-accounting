"""CLI 写命令在读取、修改、保存期间持有 GUI 单实例锁。"""

from __future__ import annotations

from functools import wraps

from ..single_instance import SingleInstanceLock
from .errors import CliError


class GuiRunning(CliError):
    # 保持已有错误码兼容；占用方也可能是另一个 CLI 写进程。
    code = "GUI_RUNNING"


def exclusive_write(handler):
    """由命令注册表统一安装，异常退出同样释放锁。"""
    @wraps(handler)
    def guarded(*args, **kwargs):
        lock = SingleInstanceLock()
        if not lock.acquire():
            raise GuiRunning(
                "桌面程序或另一条写入命令正在使用数据，已拒绝本次写入。"
                "请保存并关闭桌面程序，或等待写入命令结束后重试。",
                details={"hint": "关闭桌面程序或等待其他写入命令完成后重试"},
            )
        try:
            return handler(*args, **kwargs)
        finally:
            lock.release()
    return guarded
