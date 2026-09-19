"""CLI 写入命令测试：CRUD 全流程、安全护栏、并发保护。

每个测试用独立的临时数据目录（CPA_PROJECTS_DIR / CPA_BACKUPS_DIR），
不触碰用户真实项目。写入命令通过 subprocess 或直接调 main() 执行。
"""

import contextlib
import io
import json
import unittest

from cli_test_helpers import IsolatedDataDirTestCase

from src.cli.errors import EXIT_ERROR, EXIT_OK


def run_cli(argv: list[str]) -> tuple[int, dict]:
    """在测试进程内跑 CLI，捕获 stdout 的 JSON。"""
    from src.cli import main

    buffer = io.StringIO()
    with contextlib.redirect_stdout(buffer):
        code = main(argv)
    text = buffer.getvalue().strip()
    return code, json.loads(text) if text else {}


class TestProjectWriteCommands(IsolatedDataDirTestCase):
    def test_create_project(self):
        code, payload = run_cli(["project.create", "某某小区", "--json"])
        self.assertEqual(code, EXIT_OK)
        data = payload["data"]
        self.assertEqual(data["name"], "某某小区")
        self.assertEqual(data["status"], "editing")
        self.assertEqual(data["bill_count"], 0)
        self.assertTrue(data["uuid"])

    def test_create_rejects_blank_name(self):
        code, payload = run_cli(["project.create", "   ", "--json"])
        self.assertEqual(code, EXIT_ERROR)
        self.assertEqual(payload["error"]["code"], "INVALID_ARGUMENT")

    def test_created_project_is_visible_in_list(self):
        uuid = self.create_project("可见性")
        _code, payload = run_cli(["project.list", "--json"])
        uuids = [p["uuid"] for p in payload["data"]["projects"]]
        self.assertIn(uuid, uuids)

    def test_rename(self):
        uuid = self.create_project("旧名")
        code, payload = run_cli(["project.rename", uuid, "新名", "--json"])
        self.assertEqual(code, EXIT_OK)
        self.assertEqual(payload["data"]["name"], "新名")
        _c, show = run_cli(["project.show", uuid, "--json"])
        self.assertEqual(show["data"]["name"], "新名")

    def test_status_accepts_english_and_chinese(self):
        uuid = self.create_project("状态")
        for value, expected in (
            ("done", "done"),
            ("编辑中", "editing"),
            ("已完成", "done"),
            ("active", "editing"),
        ):
            code, payload = run_cli(["project.status", uuid, value, "--json"])
            self.assertEqual(code, EXIT_OK, payload)
            self.assertEqual(payload["data"]["status"], expected)

    def test_status_rejects_unknown_value(self):
        uuid = self.create_project("状态2")
        code, payload = run_cli(["project.status", uuid, "乱七八糟", "--json"])
        self.assertEqual(code, EXIT_ERROR)
        self.assertEqual(payload["error"]["code"], "INVALID_ARGUMENT")

    def test_delete_requires_yes_flag(self):
        uuid = self.create_project("待删")
        code, payload = run_cli(["project.delete", uuid, "--json"])
        self.assertEqual(code, EXIT_ERROR)
        self.assertEqual(payload["error"]["code"], "INVALID_ARGUMENT")
        # 未确认时项目必须仍在
        _c, show = run_cli(["project.show", uuid, "--json"])
        self.assertTrue(show["ok"])

    def test_delete_with_yes_removes_project(self):
        uuid = self.create_project("待删2")
        code, payload = run_cli(["project.delete", uuid, "--yes", "--json"])
        self.assertEqual(code, EXIT_OK)
        self.assertTrue(payload["data"]["deleted"])
        _c, show = run_cli(["project.show", uuid, "--json"])
        self.assertFalse(show["ok"])
        self.assertEqual(show["error"]["code"], "PROJECT_NOT_FOUND")

    def test_delete_creates_backup(self):
        uuid = self.create_project("备份留存")
        before = set(self.backups.iterdir())
        run_cli(["project.delete", uuid, "--yes", "--json"])
        after = set(self.backups.iterdir())
        self.assertGreater(len(after), len(before), "删除前应强制备份")


class TestBillWriteCommands(IsolatedDataDirTestCase):
    def test_add_bill_computes_total_with_unit_price(self):
        uuid = self.create_project()
        code, payload = run_cli(
            ["bill.add", uuid, "3*4+5", "--trade-item", "ti_wall", "--json"]
        )
        self.assertEqual(code, EXIT_OK)
        data = payload["data"]
        self.assertEqual(data["canonical"], "3*4+5")
        self.assertFalse(data["orphan"])
        self.assertEqual(data["name"], "砌墙")
        # 砌墙单价 45；(3*4+5)=17 -> 765
        self.assertAlmostEqual(data["total"], 765.0, places=2)

    def test_add_bill_persists_across_reload(self):
        uuid = self.create_project()
        self.add_bill(uuid, "2+2")
        _c, payload = run_cli(["bill.summary", uuid, "--json"])
        self.assertEqual(payload["data"]["bill_count"], 1)
        self.assertAlmostEqual(payload["data"]["total"], 4 * 45.0, places=2)

    def test_add_bill_requires_trade_item_or_explicit_orphan(self):
        uuid = self.create_project()
        code, payload = run_cli(["bill.add", uuid, "1+1", "--json"])
        self.assertEqual(code, EXIT_ERROR)
        self.assertEqual(payload["error"]["code"], "INVALID_ARGUMENT")
        self.assertIn("available", payload["error"]["details"])

    def test_add_orphan_bill_when_explicitly_allowed(self):
        uuid = self.create_project()
        code, payload = run_cli(["bill.add", uuid, "1+1", "--allow-orphan", "--json"])
        self.assertEqual(code, EXIT_OK)
        self.assertTrue(payload["data"]["orphan"])

    def test_add_bill_rejects_unknown_trade_item(self):
        uuid = self.create_project()
        code, payload = run_cli(
            ["bill.add", uuid, "1+1", "--trade-item", "ti_不存在", "--json"]
        )
        self.assertEqual(code, EXIT_ERROR)
        self.assertEqual(payload["error"]["code"], "INVALID_ARGUMENT")

    def test_update_content_recomputes_total(self):
        uuid = self.create_project()
        bill_id = self.add_bill(uuid, "2+1")
        code, payload = run_cli(
            ["bill.update", uuid, bill_id, "--content", "10*2", "--json"]
        )
        self.assertEqual(code, EXIT_OK)
        self.assertTrue(payload["data"]["changed"])
        self.assertAlmostEqual(payload["data"]["total"], 20 * 45.0, places=2)

    def test_update_with_no_changes_reports_changed_false(self):
        uuid = self.create_project()
        bill_id = self.add_bill(uuid, "2+1")
        code, payload = run_cli(
            ["bill.update", uuid, bill_id, "--content", "2+1", "--json"]
        )
        self.assertEqual(code, EXIT_OK)
        self.assertFalse(payload["data"]["changed"])

    def test_update_reviewed_flag(self):
        uuid = self.create_project()
        bill_id = self.add_bill(uuid)
        code, payload = run_cli(["bill.update", uuid, bill_id, "--reviewed", "--json"])
        self.assertEqual(code, EXIT_OK)
        self.assertTrue(payload["data"]["reviewed"])

    def test_reviewed_is_tristate(self):
        """--reviewed / --no-reviewed / 不传 必须可区分。

        回归：--reviewed 曾是普通 store_true 旗标，默认 False，
        导致无法取消审核（只能设 True）。
        """
        uuid = self.create_project()
        bill_id = self.add_bill(uuid)

        # 设为已审核
        _c, on = run_cli(["bill.update", uuid, bill_id, "--reviewed", "--json"])
        self.assertTrue(on["data"]["reviewed"])

        # 取消审核（修复前做不到）
        c_off, off = run_cli(["bill.update", uuid, bill_id, "--no-reviewed", "--json"])
        self.assertEqual(c_off, EXIT_OK, off)
        self.assertFalse(off["data"]["reviewed"])
        self.assertTrue(off["data"]["changed"])

        # 不传则不改动（content 与现状相同，避免引入无关改动）
        _c, untouched = run_cli(
            ["bill.update", uuid, bill_id, "--content", "3*4", "--json"]
        )
        self.assertFalse(untouched["data"]["reviewed"])
        self.assertFalse(untouched["data"]["changed"])

    def test_remove_bill(self):
        uuid = self.create_project()
        bill_id = self.add_bill(uuid)
        code, payload = run_cli(["bill.remove", uuid, bill_id, "--json"])
        self.assertEqual(code, EXIT_OK)
        self.assertEqual(payload["data"]["remaining"], 0)
        _c, summary = run_cli(["bill.summary", uuid, "--json"])
        self.assertEqual(summary["data"]["bill_count"], 0)

    def test_remove_unknown_bill_reports_not_found(self):
        uuid = self.create_project()
        code, payload = run_cli(["bill.remove", uuid, "b_不存在", "--json"])
        self.assertEqual(code, EXIT_ERROR)
        self.assertEqual(payload["error"]["code"], "PROJECT_NOT_FOUND")

    def test_add_bill_rejected_on_finished_project(self):
        uuid = self.create_project()
        run_cli(["project.status", uuid, "done", "--json"])
        code, payload = run_cli(
            ["bill.add", uuid, "1+1", "--trade-item", "ti_wall", "--json"]
        )
        self.assertEqual(code, EXIT_ERROR)
        self.assertEqual(payload["error"]["code"], "INVALID_ARGUMENT")
        self.assertIn("已完成", payload["error"]["message"])

    def test_removed_bill_no_longer_counted(self):
        uuid = self.create_project()
        keep = self.add_bill(uuid, "1*1")
        drop = self.add_bill(uuid, "9*9")
        run_cli(["bill.remove", uuid, drop, "--json"])
        _c, payload = run_cli(["bill.summary", uuid, "--json"])
        self.assertEqual(payload["data"]["bill_count"], 1)
        self.assertAlmostEqual(payload["data"]["total"], 1 * 45.0, places=2)
        self.assertTrue(keep)


class TestWriteGuards(IsolatedDataDirTestCase):
    def test_lock_blocks_another_process_for_entire_write(self):
        import subprocess
        import sys
        from src.cli.guard import exclusive_write

        probe = (
            "from src.single_instance import SingleInstanceLock; "
            "lock = SingleInstanceLock(); acquired = lock.acquire(); "
            "lock.release(); raise SystemExit(0 if acquired else 3)"
        )

        @exclusive_write
        def write():
            result = subprocess.run([sys.executable, "-c", probe], timeout=10)
            self.assertEqual(result.returncode, 3)

        write()
        result = subprocess.run([sys.executable, "-c", probe], timeout=10)
        self.assertEqual(result.returncode, 0)

    def test_zero_formula_has_consistent_error_count(self):
        uuid = self.create_project()
        self.add_bill(uuid, "1-1")
        for command in ("bill.list", "bill.summary"):
            code, payload = run_cli([command, uuid, "--json"])
            self.assertEqual(code, EXIT_OK, payload)
            self.assertEqual(payload["data"]["formula_error_count"], 0)

    def test_write_rejected_while_gui_lock_held(self):
        """模拟 GUI 运行：写入应被拒绝，只读仍可用。"""
        from src.single_instance import SingleInstanceLock

        lock = SingleInstanceLock()
        if not lock.acquire():  # pragma: no cover - 环境不支持文件锁时跳过
            self.skipTest("无法获取单实例锁")
        try:
            code, payload = run_cli(["project.create", "应被拒绝", "--json"])
            self.assertEqual(code, EXIT_ERROR)
            self.assertEqual(payload["error"]["code"], "GUI_RUNNING")

            # 只读命令不应受影响
            code_ro, payload_ro = run_cli(["project.list", "--json"])
            self.assertEqual(code_ro, EXIT_OK, payload_ro)
        finally:
            lock.release()

    def test_write_succeeds_after_gui_lock_released(self):
        from src.single_instance import SingleInstanceLock

        lock = SingleInstanceLock()
        self.assertTrue(lock.acquire())
        lock.release()
        code, payload = run_cli(["project.create", "释放后可写", "--json"])
        self.assertEqual(code, EXIT_OK, payload)

    def test_registered_write_holds_lock_until_handler_returns(self):
        from src.cli.registry import get_command
        from src.cli.guard import exclusive_write
        from src.single_instance import SingleInstanceLock

        for fail in (False, True):
            def handler(args):
                contender = SingleInstanceLock()
                try:
                    self.assertFalse(contender.acquire())
                finally:
                    contender.release()
                if fail:
                    raise ValueError("failure")
                return "ok"

            spec = get_command("project.create")
            self.assertTrue(hasattr(spec.handler, "__wrapped__"))
            guarded = exclusive_write(handler)
            if fail:
                with self.assertRaises(ValueError):
                    guarded(None)
            else:
                self.assertEqual(guarded(None), "ok")
            released = SingleInstanceLock()
            try:
                self.assertTrue(released.acquire())
            finally:
                released.release()

    def test_all_writes_are_guarded_and_reads_are_unwrapped(self):
        from src.cli.registry import all_commands
        for spec in all_commands():
            self.assertEqual(hasattr(spec.handler, "__wrapped__"), not spec.read_only)


if __name__ == "__main__":
    unittest.main()
