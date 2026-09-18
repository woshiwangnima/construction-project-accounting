"""CLI 命令集合。导入即注册（`src/cli/__init__.py` 负责触发）。"""
from __future__ import annotations

from . import backup, bill, calc, project, schema

__all__ = ["backup", "bill", "calc", "project", "schema"]
