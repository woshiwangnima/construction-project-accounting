"""ProjectSaveBridge：异步项目保存桥（自 content.py 抽出）。

快照合并 + 单 worker 串行写入 + 状态信号。宿主销毁前必须 close()。
"""
import copy
import threading

from PySide6.QtCore import QObject, Signal

from ...logger import logger
from ...project_manager import update_project


class ProjectSaveBridge(QObject):
    """异步项目保存桥：快照合并 + 单 worker 串行写入 + 状态信号。"""

    save_error = Signal(str)
    save_state = Signal(str, str)  # (state, stamp)：saving/saved/failed

    def __init__(self, parent=None):
        super().__init__(parent)
        self._lock = threading.Lock()
        self._pending: tuple[str, dict] | None = None
        self._running = False
        self._closed = False
        self._idle = threading.Event()
        self._idle.set()

    def close(self, timeout: float = 2.0) -> None:
        """关闭保存桥：丢弃未写入的排队任务并等 worker 退出。

        必须在宿主 QObject 销毁前调用；否则后台线程可能在 C++ 对象
        已删除后 emit 信号，抛 RuntimeError 并打断 drain 循环。
        """
        with self._lock:
            self._closed = True
            self._pending = None
        self._idle.wait(max(float(timeout), 0.0))

    def schedule(self, uuid: str, project_data) -> None:
        if not uuid or not project_data:
            return
        try:
            snapshot = copy.deepcopy(project_data)
        except Exception:
            snapshot = (project_data.to_dict()
                        if hasattr(project_data, "to_dict")
                        else dict(project_data))
        with self._lock:
            if self._closed:
                return
            self._pending = (uuid, snapshot)
            self._idle.clear()
            if self._running:
                return
            self._running = True
            self._emit("saving", "")
        threading.Thread(target=self._drain, name="project-save", daemon=True).start()

    def _emit(self, state: str, stamp: str) -> None:
        """安全 emit：宿主已删除时静默降级为日志，不打断 worker。"""
        try:
            self.save_state.emit(state, stamp)
        except RuntimeError:
            logger.debug("[save-bridge] receiver deleted, drop %s signal", state)

    def _drain(self) -> None:
        while True:
            with self._lock:
                pending = self._pending
                self._pending = None
                if pending is None:
                    self._running = False
                    self._idle.set()
                    return
            uuid, snapshot = pending
            try:
                update_project(uuid, snapshot)
                from .feedback import now_stamp
                self._emit("saved", now_stamp())
            except Exception as exc:  # pragma: no cover - defensive worker boundary
                logger.warning("项目后台保存失败 uuid=%s: %s", uuid[:16], exc, exc_info=True)
                try:
                    self.save_error.emit(str(exc))
                except RuntimeError:
                    pass
                self._emit("failed", "")

    def flush(self, timeout: float = 2.0) -> bool:
        return self._idle.wait(max(float(timeout), 0.0))
