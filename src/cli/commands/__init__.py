"""CLI 命令集合。导入即注册（`src/cli/__init__.py` 负责触发）。"""

from __future__ import annotations

from . import (
    backup,
    bill,
    bill_write,
    calc,
    project,
    project_write,
    schema,
    trade,
)

__all__ = [
    "backup",
    "bill",
    "bill_write",
    "calc",
    "project",
    "project_write",
    "schema",
    "trade",
]
