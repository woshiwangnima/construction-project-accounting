"""CLI 输出契约测试。

“说明书”要能被其他程序依赖，前提是契约本身有测试守住。这里覆盖：

- 注册表与 argparse / schema 三者一致（防漏登记、防手写文档漂移）
- 成功 / 失败响应体结构（ok / data / error.code / error.message）
- 退出码约定
- 关键业务口径（单价乘法、孤儿回退 frozen_total）与 GUI 一致
"""
import argparse
import io
import json
import unittest
from contextlib import redirect_stdout
from unittest.mock import patch

from src.cli import main
from src.cli.errors import EXIT_ERROR, EXIT_OK, EXIT_USAGE
from src.cli.registry import all_commands, build_schema


def _args(**kwargs) -> argparse.Namespace:
    """构造与 argparse 一致的 Namespace，避免自定义替身与类型标注不符。"""
    return argparse.Namespace(**kwargs)


def run_cli(argv: list[str]) -> tuple[int, dict]:
    """跑一次 CLI，捕获 stdout 的 JSON。"""
    buffer = io.StringIO()
    with redirect_stdout(buffer):
        code = main(argv)
    text = buffer.getvalue().strip()
    return code, json.loads(text) if text else {}


class TestRegistryConsistency(unittest.TestCase):
    def test_schema_lists_every_registered_command(self):
        names = [spec.name for spec in all_commands()]
        schema_names = [cmd["name"] for cmd in build_schema()["commands"]]
        self.assertEqual(sorted(names), sorted(schema_names))
        self.assertTrue(names, "注册表为空")

    def test_expected_commands_are_registered(self):
        names = {spec.name for spec in all_commands()}
        for expected in (
            "schema",
            "calc",
            "project.list",
            "project.show",
            "project.export",
            "project.import",
            "bill.list",
            "bill.summary",
            "backup.list",
            "backup.inspect",
        ):
            self.assertIn(expected, names)

    def test_no_duplicate_command_names(self):
        names = [spec.name for spec in all_commands()]
        self.assertEqual(len(names), len(set(names)))

    def test_every_command_has_help_and_handler(self):
        for spec in all_commands():
            self.assertTrue(spec.help, f"{spec.name} 缺少 help")
            self.assertTrue(callable(spec.handler), f"{spec.name} 缺少 handler")


class TestResponseContract(unittest.TestCase):
    def test_success_shape(self):
        code, payload = run_cli(["calc", "1+1", "--json"])
        self.assertEqual(code, EXIT_OK)
        self.assertIs(payload["ok"], True)
        self.assertIn("data", payload)
        self.assertNotIn("error", payload)

    def test_failure_shape_keeps_json_and_exit_code(self):
        code, payload = run_cli(["project.show", "not-a-uuid", "--json"])
        self.assertEqual(code, EXIT_ERROR)
        self.assertIs(payload["ok"], False)
        self.assertIn("error", payload)
        self.assertNotIn("data", payload)
        self.assertIsInstance(payload["error"]["code"], str)
        self.assertIsInstance(payload["error"]["message"], str)
        self.assertTrue(payload["error"]["message"])

    def test_project_not_found_code_is_stable(self):
        _code, payload = run_cli(["project.show", "not-a-uuid", "--json"])
        self.assertEqual(payload["error"]["code"], "PROJECT_NOT_FOUND")

    def test_formula_error_code_is_stable(self):
        code, payload = run_cli(["calc", "3++*", "--json"])
        self.assertEqual(code, EXIT_ERROR)
        self.assertEqual(payload["error"]["code"], "FORMULA_ERROR")

    def test_unknown_project_returns_json_not_traceback(self):
        code, payload = run_cli(["bill.summary", "target-does-not-exist", "--json"])
        self.assertEqual(code, EXIT_ERROR)
        self.assertIs(payload["ok"], False)

    def test_missing_argument_is_usage_error(self):
        with self.assertRaises(SystemExit) as ctx:
            run_cli(["project.show"])
        self.assertEqual(ctx.exception.code, EXIT_USAGE)

    def test_no_command_prints_help(self):
        self.assertEqual(main([]), EXIT_USAGE)

    def test_schema_is_self_describing(self):
        code, payload = run_cli(["schema", "--json"])
        self.assertEqual(code, EXIT_OK)
        data = payload["data"]
        self.assertIn("responseContract", data)
        self.assertIn("exitCodes", data["responseContract"])
        self.assertTrue(data["commands"])


class TestBusinessParity(unittest.TestCase):
    """CLI 金额口径必须与 GUI 一致（复用同一批 domain 函数）。"""

    def test_unit_price_multiplication_matches_gui_formula(self):
        from src.bill_recompute import summarize_bill_calculations
        from src.cli.common import op_map

        bills = [{"id": "b1", "trade_item_id": "ti1", "content": "2+1", "note": ""}]
        items = [{"id": "ti1", "name": "砌墙", "has_unit": True, "unit_price": 12.5, "unit": "m2"}]
        _calcs, total, errors = summarize_bill_calculations(bills, items, op_map())
        self.assertAlmostEqual(total, 37.5, places=2)
        self.assertEqual(errors, 0)

    def test_orphan_falls_back_to_frozen_total(self):
        from src.bill_recompute import summarize_bill_calculations
        from src.cli.common import op_map

        bills = [{"id": "b1", "trade_item_id": "ghost", "content": "5*2",
                  "note": "", "frozen_total": 99.0}]
        calcs, total, _errors = summarize_bill_calculations(bills, [], op_map())
        self.assertTrue(calcs[0].orphan)
        self.assertAlmostEqual(total, 99.0, places=2)

    def test_calc_normalizes_fullwidth_symbols(self):
        code, payload = run_cli(["calc", "（2+3）×4", "--json"])
        self.assertEqual(code, EXIT_OK)
        self.assertEqual(payload["data"]["canonical"], "(2+3)*4")
        self.assertAlmostEqual(payload["data"]["result"], 20.0, places=2)

    def test_calc_amount_uses_two_decimals(self):
        _code, payload = run_cli(["calc", "1/3", "--json"])
        self.assertEqual(payload["data"]["amount"], round(1 / 3, 2))


class TestBillListFiltering(unittest.TestCase):
    def test_totals_are_filtered_handlers(self):
        """筛选后 total 必须只统计实际输出的行。"""
        from src.cli.commands import bill as bill_module

        class _Project:
            project_uuid = "u1"
            name = "t"
            status = "editing"

            @property
            def bills(self):
                return []

            trade_items = []

        with patch.object(bill_module, "require_project", return_value=_Project()):
            from src.bill_recompute import BillCalculation
            from src.billing import Billing

            rows = [
                {"id": "b1", "trade_item_id": "ti1", "content": "2+1"},
                {"id": "b2", "trade_item_id": "ghost", "content": "5*2"},
            ]
            calcs = [
                BillCalculation(total=37.5, canonical="2+1", formula_value=None,
                                formula_error=False, trade_item=None,
                                billing=Billing(), category="", name="砌墙", orphan=False),
                BillCalculation(total=99.0, canonical="5*2", formula_value=None,
                                formula_error=False, trade_item=None,
                                billing=Billing(), category="", name="", orphan=True),
            ]
            with patch.object(bill_module, "_bill_rows", return_value=rows), \
                 patch.object(bill_module, "_trade_item_rows", return_value=[]), \
                 patch.object(bill_module, "summarize_bill_calculations",
                              return_value=(calcs, 136.5, 0)):
                result = bill_module._bill_list(_args(uuid="u1", orphan_only=True))

        self.assertEqual(result["count"], 1)
        self.assertAlmostEqual(result["total"], 99.0, places=2)
        self.assertAlmostEqual(result["project_total"], 136.5, places=2)


if __name__ == "__main__":
    unittest.main()
