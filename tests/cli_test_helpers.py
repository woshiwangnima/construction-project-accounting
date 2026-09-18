"""CLI 测试共用的隔离环境与执行助手。

放在独立模块而不是 test_*.py 里，避免测试文件之间互相 import
（tests/ 不是包，`from tests.x import y` 在 unittest discover 下会失败）。

关键点：必须同时重定向 `CPA_DATA_DIR`。单实例锁（GUI 运行检测）
位于 `get_data_dir()`，若不重定向，测试会去碰用户真实的 `.app.lock`——
用户开着桌面程序时，所有写入测试都会被正确地拒绝而集体失败。
"""
from __future__ import annotations

import contextlib
import io
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


def run_cli(argv: list[str]) -> tuple[int, dict]:
    """在测试进程内跑 CLI，捕获 stdout 的 JSON。"""
    from src.cli import main

    buffer = io.StringIO()
    with contextlib.redirect_stdout(buffer):
        code = main(argv)
    text = buffer.getvalue().strip()
    return code, json.loads(text) if text else {}


class IsolatedDataDirTestCase(unittest.TestCase):
    """把项目/备份/数据目录全部指向临时目录。"""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        root = Path(self._tmp.name)
        self.projects = root / "projects"
        self.backups = root / "backups"
        self.projects.mkdir()
        self.backups.mkdir()
        self._env = patch.dict(
            os.environ,
            {
                "CPA_DATA_DIR": str(root),
                "CPA_PROJECTS_DIR": str(self.projects),
                "CPA_BACKUPS_DIR": str(self.backups),
            },
        )
        self._env.start()

    def tearDown(self):
        self._env.stop()
        self._tmp.cleanup()

    # ── 常用操作 ───────────────────────────────────────────────────────

    def create_project(self, name: str = "测试项目") -> str:
        from src.cli.errors import EXIT_OK

        code, payload = run_cli(["project.create", name, "--json"])
        self.assertEqual(code, EXIT_OK, payload)
        return payload["data"]["uuid"]

    def add_bill(
        self, uuid: str, content: str = "3*4", trade_item: str = "ti_wall"
    ) -> str:
        from src.cli.errors import EXIT_OK

        code, payload = run_cli(
            ["bill.add", uuid, content, "--trade-item", trade_item, "--json"]
        )
        self.assertEqual(code, EXIT_OK, payload)
        return payload["data"]["id"]
