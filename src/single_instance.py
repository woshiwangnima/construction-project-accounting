"""单实例锁，避免多个程序同时覆盖同一批 JSON 数据。"""
from __future__ import annotations

import os
import re
from pathlib import Path

from .paths import get_data_dir


class SingleInstanceLock:
    def __init__(self, name: str = "app"):
        if not isinstance(name, str) or not re.fullmatch(r"[A-Za-z0-9_-]+", name):
            raise ValueError("单实例锁名称只能包含字母、数字、下划线或连字符")
        self.path = get_data_dir() / f".{name}.lock"
        self._file = None
        self._locked = False

    def acquire(self) -> bool:
        if self._file is not None:
            return self._locked
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self._file = open(self.path, "a+b")
            # msvcrt.locking/fcntl both need an existing byte at offset zero.
            # Do not write on every launch: append mode would otherwise grow
            # the lock file indefinitely over repeated starts.
            if os.fstat(self._file.fileno()).st_size == 0:
                self._file.write(b"0")
                self._file.flush()
            self._file.seek(0)
            if os.name == "nt":
                import msvcrt
                msvcrt.locking(self._file.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(self._file.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            self._locked = True
            return True
        except (OSError, ImportError):
            self.release()
            return False

    def release(self) -> None:
        if self._file is None:
            return
        try:
            if self._locked:
                if os.name == "nt":
                    import msvcrt
                    self._file.seek(0)
                    msvcrt.locking(self._file.fileno(), msvcrt.LK_UNLCK, 1)
                else:
                    import fcntl
                    fcntl.flock(self._file.fileno(), fcntl.LOCK_UN)
        except (OSError, ImportError):
            pass
        finally:
            self._locked = False
            self._file.close()
            self._file = None

    def __enter__(self):
        if not self.acquire():
            raise RuntimeError("应用程序已经在运行")
        return self

    def __exit__(self, exc_type, exc, tb):
        self.release()
