"""`trade` 命令测试：工种与单价管理。

覆盖关键语义：改单价会**实时重算**已有账单金额（GUI 既有行为），
以及由此产生的可见影响回报（affected_bills / total_delta）。
"""

import unittest

from cli_test_helpers import IsolatedDataDirTestCase, run_cli

from src.cli.errors import EXIT_ERROR, EXIT_OK


class TestTradeList(IsolatedDataDirTestCase):
    def test_lists_default_trade_items_with_prices(self):
        uuid = self.create_project()
        code, payload = run_cli(["trade.list", uuid, "--json"])
        self.assertEqual(code, EXIT_OK)
        data = payload["data"]
        self.assertGreater(data["count"], 0)
        wall = [t for t in data["trade_items"] if t["id"] == "ti_wall"]
        self.assertTrue(wall, "默认工种应包含 ti_wall")
        self.assertEqual(wall[0]["name"], "砌墙")
        self.assertAlmostEqual(wall[0]["unit_price"], 45.0, places=2)

    def test_filter_by_name(self):
        uuid = self.create_project()
        code, payload = run_cli(
            ["trade.list", uuid, "--name-contains", "砌墙", "--json"]
        )
        self.assertEqual(code, EXIT_OK)
        self.assertEqual(payload["data"]["count"], 1)


class TestTradeAdd(IsolatedDataDirTestCase):
    def test_add_per_unit_trade(self):
        uuid = self.create_project()
        code, payload = run_cli(
            [
                "trade.add",
                uuid,
                "--name",
                "找平",
                "--unit-price",
                "25",
                "--unit",
                "m2",
                "--json",
            ]
        )
        self.assertEqual(code, EXIT_OK, payload)
        data = payload["data"]
        self.assertEqual(data["name"], "找平")
        self.assertTrue(data["has_unit"])
        self.assertAlmostEqual(data["unit_price"], 25.0, places=2)
        self.assertEqual(data["unit"], "m2")
        self.assertTrue(data["id"])

    def test_add_decimal_price(self):
        uuid = self.create_project()
        code, payload = run_cli(
            ["trade.add", uuid, "--name", "抹灰", "--unit-price", "12.5", "--json"]
        )
        self.assertEqual(code, EXIT_OK, payload)
        self.assertAlmostEqual(payload["data"]["unit_price"], 12.5, places=2)

    def test_add_no_unit_trade(self):
        uuid = self.create_project()
        code, payload = run_cli(
            ["trade.add", uuid, "--name", "杂项", "--no-unit", "--json"]
        )
        self.assertEqual(code, EXIT_OK, payload)
        self.assertFalse(payload["data"]["has_unit"])
        self.assertEqual(payload["data"]["price_display"], "无单价")

    def test_add_requires_price_when_per_unit(self):
        uuid = self.create_project()
        code, payload = run_cli(["trade.add", uuid, "--name", "缺价", "--json"])
        self.assertEqual(code, EXIT_ERROR)
        self.assertEqual(payload["error"]["code"], "INVALID_ARGUMENT")

    def test_add_rejects_duplicate_name(self):
        uuid = self.create_project()
        code, payload = run_cli(
            ["trade.add", uuid, "--name", "砌墙", "--unit-price", "10", "--json"]
        )
        self.assertEqual(code, EXIT_ERROR)
        self.assertEqual(payload["error"]["code"], "INVALID_ARGUMENT")

    def test_add_rejects_blank_name(self):
        uuid = self.create_project()
        code, _payload = run_cli(
            ["trade.add", uuid, "--name", "  ", "--unit-price", "10", "--json"]
        )
        self.assertEqual(code, EXIT_ERROR)

    def test_add_creates_category_when_missing(self):
        uuid = self.create_project()
        code, payload = run_cli(
            [
                "trade.add",
                uuid,
                "--name",
                "刷漆",
                "--unit-price",
                "18",
                "--category",
                "油漆工程",
                "--json",
            ]
        )
        self.assertEqual(code, EXIT_OK, payload)
        self.assertEqual(payload["data"]["category"], "油漆工程")
        self.assertTrue(payload["data"]["category_id"])
        _c, lst = run_cli(["trade.list", uuid, "--json"])
        self.assertIn("油漆工程", lst["data"]["categories"])

    def test_new_trade_is_usable_by_bill_add(self):
        uuid = self.create_project()
        _c, added = run_cli(
            ["trade.add", uuid, "--name", "找平", "--unit-price", "25", "--json"]
        )
        trade_id = added["data"]["id"]
        code, bill = run_cli(
            ["bill.add", uuid, "10*2", "--trade-item", trade_id, "--json"]
        )
        self.assertEqual(code, EXIT_OK, bill)
        self.assertAlmostEqual(bill["data"]["total"], 500.0, places=2)


class TestTradeUpdate(IsolatedDataDirTestCase):
    def test_price_change_recalculates_existing_bills(self):
        """改价会实时改变已有账单金额 —— GUI 既有语义，CLI 必须一致。"""
        uuid = self.create_project()
        self.add_bill(uuid, "2+1")  # 3 * 45 = 135
        self.add_bill(uuid, "1*1")  # 1 * 45 = 45

        code, payload = run_cli(
            ["trade.update", uuid, "ti_wall", "--unit-price", "50", "--json"]
        )
        self.assertEqual(code, EXIT_OK, payload)
        data = payload["data"]
        self.assertEqual(data["affected_bills"], 2)
        self.assertAlmostEqual(data["total_before"], 180.0, places=2)
        self.assertAlmostEqual(data["total_after"], 200.0, places=2)
        self.assertAlmostEqual(data["total_delta"], 20.0, places=2)

        _c, summary = run_cli(["bill.summary", uuid, "--json"])
        self.assertAlmostEqual(summary["data"]["total"], 200.0, places=2)

    def test_update_name(self):
        uuid = self.create_project()
        code, payload = run_cli(
            ["trade.update", uuid, "ti_wall", "--name", "砌砖墙", "--json"]
        )
        self.assertEqual(code, EXIT_OK)
        self.assertEqual(payload["data"]["after"]["name"], "砌砖墙")

    def test_update_unit(self):
        uuid = self.create_project()
        code, payload = run_cli(
            ["trade.update", uuid, "ti_wall", "--unit", "m3", "--json"]
        )
        self.assertEqual(code, EXIT_OK)
        self.assertEqual(payload["data"]["after"]["unit"], "m3")

    def test_update_to_no_unit(self):
        uuid = self.create_project()
        code, payload = run_cli(
            ["trade.update", uuid, "ti_wall", "--no-unit", "--json"]
        )
        self.assertEqual(code, EXIT_OK)
        after = payload["data"]["after"]
        self.assertFalse(after["has_unit"])
        self.assertEqual(after["price_display"], "无单价")

    def test_update_requires_at_least_one_field(self):
        uuid = self.create_project()
        code, payload = run_cli(["trade.update", uuid, "ti_wall", "--json"])
        self.assertEqual(code, EXIT_ERROR)
        self.assertEqual(payload["error"]["code"], "INVALID_ARGUMENT")

    def test_update_rejects_negative_price(self):
        uuid = self.create_project()
        code, payload = run_cli(
            ["trade.update", uuid, "ti_wall", "--unit-price", "-5", "--json"]
        )
        self.assertEqual(code, EXIT_ERROR)
        self.assertEqual(payload["error"]["code"], "INVALID_ARGUMENT")

    def test_update_unknown_trade_reports_not_found(self):
        uuid = self.create_project()
        code, payload = run_cli(
            ["trade.update", uuid, "ti_不存在", "--unit-price", "10", "--json"]
        )
        self.assertEqual(code, EXIT_ERROR)
        self.assertEqual(payload["error"]["code"], "PROJECT_NOT_FOUND")
        self.assertIn("available", payload["error"]["details"])

    def test_update_rejected_on_finished_project(self):
        uuid = self.create_project()
        run_cli(["project.status", uuid, "done", "--json"])
        code, payload = run_cli(
            ["trade.update", uuid, "ti_wall", "--unit-price", "99", "--json"]
        )
        self.assertEqual(code, EXIT_ERROR)
        self.assertIn("已完成", payload["error"]["message"])

    def test_price_change_persists(self):
        uuid = self.create_project()
        run_cli(["trade.update", uuid, "ti_wall", "--unit-price", "77", "--json"])
        _c, payload = run_cli(["trade.list", uuid, "--json"])
        wall = next(t for t in payload["data"]["trade_items"] if t["id"] == "ti_wall")
        self.assertAlmostEqual(wall["unit_price"], 77.0, places=2)


class TestTradeWriteGuards(IsolatedDataDirTestCase):
    def test_trade_add_rejected_while_gui_running(self):
        from src.single_instance import SingleInstanceLock

        uuid = self.create_project()
        lock = SingleInstanceLock()
        if not lock.acquire():  # pragma: no cover
            self.skipTest("无法获取单实例锁")
        try:
            code, payload = run_cli(
                ["trade.add", uuid, "--name", "X", "--unit-price", "1", "--json"]
            )
            self.assertEqual(code, EXIT_ERROR)
            self.assertEqual(payload["error"]["code"], "GUI_RUNNING")
        finally:
            lock.release()

    def test_trade_list_works_while_gui_running(self):
        from src.single_instance import SingleInstanceLock

        uuid = self.create_project()
        lock = SingleInstanceLock()
        if not lock.acquire():  # pragma: no cover
            self.skipTest("无法获取单实例锁")
        try:
            code, payload = run_cli(["trade.list", uuid, "--json"])
            self.assertEqual(code, EXIT_OK, payload)
        finally:
            lock.release()


if __name__ == "__main__":
    unittest.main()
