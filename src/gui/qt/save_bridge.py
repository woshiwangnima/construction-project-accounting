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
        self._pending: dict[str, object] = {}
        self._failed: dict[str, object] = {}
        self._inflight: tuple[str, object] | None = None
        self._running = False
        self._closed = False
        self._idle = threading.Event()
        self._idle.set()

    def close(self, timeout: float = 2.0) -> bool:
        """保存完成才关闭；超时或失败时保留快照，允许再次编辑和重试。

        必须在宿主 QObject 销毁前调用；否则后台线程可能在 C++ 对象
        已删除后 emit 信号，抛 RuntimeError 并打断 drain 循环。
        """
        if not self.flush(timeout):
            return False
        with self._lock:
            if self._running or self._pending or self._failed:
                return False
            self._closed = True
        return True

    def schedule(self, uuid: str, project_data) -> None:
        if not uuid or not project_data:
            return
        try:
            snapshot = copy.deepcopy(project_data)
        except Exception:
            snapshot = (project_data.to_dict()
                        if hasattr(project_data, "to_dict")
                        else dict(project_data))
        if hasattr(snapshot, "to_dict"):
            snapshot = snapshot.to_dict()
        with self._lock:
            if self._closed:
                return
            self._pending[uuid] = snapshot
            self._failed.pop(uuid, None)
            self._idle.clear()
            if self._running:
                return
            self._running = True
        self._emit("saving", "")
        threading.Thread(target=self._drain, name="project-save", daemon=True).start()

    def pending_snapshot(self, uuid: str):
        """Read the latest unsaved data when switching back to a project."""
        with self._lock:
            snapshot = self._pending.get(uuid, self._failed.get(uuid))
            if snapshot is None and self._inflight and self._inflight[0] == uuid:
                snapshot = self._inflight[1]
            return copy.deepcopy(snapshot)

    def _emit(self, state: str, stamp: str) -> None:
        """安全 emit：宿主已删除时静默降级为日志，不打断 worker。"""
        try:
            self.save_state.emit(state, stamp)
        except RuntimeError:
            logger.debug("[save-bridge] receiver deleted, drop %s signal", state)

    def _drain(self) -> None:
        while True:
            with self._lock:
                if not self._pending:
                    self._running = False
                    # Signal delivery must finish before close() can destroy us.
                    state = "failed" if self._failed else "saved"
                    from .feedback import now_stamp
                    self._emit(state, now_stamp() if state == "saved" else "")
                    self._idle.set()
                    return
                uuid = next(iter(self._pending))
                snapshot = self._pending.pop(uuid)
                self._inflight = (uuid, snapshot)
            try:
                update_project(uuid, snapshot)
            except Exception as exc:  # pragma: no cover - defensive worker boundary
                with self._lock:
                    if uuid not in self._pending:
                        self._failed[uuid] = snapshot
                logger.warning("项目后台保存失败 uuid=%s: %s", uuid[:16], exc, exc_info=True)
                try:
                    self.save_error.emit(str(exc))
                except RuntimeError:
                    pass
                self._emit("failed", "")
            finally:
                with self._lock:
                    self._inflight = None

    def flush(self, timeout: float = 2.0) -> bool:
        """重试此前失败的快照；只有全部成功落盘才返回 True。"""
        start_worker = False
        with self._lock:
            self._pending.update(self._failed)
            self._failed.clear()
            if self._pending and not self._running:
                self._running = True
                self._idle.clear()
                start_worker = True
        if start_worker:
            self._emit("saving", "")
            threading.Thread(target=self._drain, name="project-save", daemon=True).start()
        if not self._idle.wait(max(float(timeout), 0.0)):
            return False
        with self._lock:
            return not (self._running or self._pending or self._failed)
