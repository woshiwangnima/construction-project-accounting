"""GUI 运行检测（并发写入保护）。

问题
----
GUI 与 CLI 都能写同一批项目 JSON。若用户在桌面程序里编辑项目的同时，
另一个进程用 CLI 写入，两边的内存快照会互相覆盖——用户的编辑可能丢失。

方案（与用户确认的 a 方案）
--------------------------
CLI 写入前先尝试获取 GUI 使用的同一把单实例锁（`SingleInstanceLock`）：
- 拿得到 → 说明 GUI 没在运行，安全；**立即释放**，因为 CLI 是短进程，
  不应该长期占着这把锁（否则用户随后启动 GUI 会被拒）。
- 拿不到 → GUI 正在运行，拒绝写入并给出明确提示。

只读命令不调用这里，因此 GUI 开着也能正常查询。
"""

from __future__ import annotations

from ..single_instance import SingleInstanceLock
from .errors import CliError


class GuiRunning(CliError):
    code = "GUI_RUNNING"


def ensure_gui_not_running() -> None:
    """GUI 正在运行时抛 GuiRunning；否则立即释放探测锁并返回。"""
    lock = SingleInstanceLock()
    if not lock.acquire():
        raise GuiRunning(
            "检测到桌面程序正在运行，为避免覆盖你正在编辑的数据，"
            "已拒绝本次写入。请先保存并关闭程序后重试。",
            details={"hint": "关闭「施工项目记账程序」后重新执行本命令"},
        )
    # 探测成功即释放：CLI 不该长期持有 GUI 的锁。
    lock.release()
