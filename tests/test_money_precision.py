import unittest
from decimal import Decimal

from src.bill_recompute import recompute_bill_total, summarize_bill_calculations
from src.calculator import evaluate_decimal


class MoneyPrecisionTests(unittest.TestCase):
    def test_summary_adds_rounded_amounts_without_float_drift(self):
        bills = [{"trade_item_id": "ti", "content": "0.1"} for _ in range(10)]
        _, total, _ = summarize_bill_calculations(bills, [{"id": "ti", "has_unit": False}], {})
        self.assertEqual(total, 1.0)

    def test_expression_evaluation_uses_decimal_arithmetic(self):
        self.assertEqual(evaluate_decimal("0.1+0.2"), Decimal("0.3"))

    def test_bill_total_is_rounded_to_cents_without_float_drift(self):
        trade_items = [{
            "id": "ti-1",
            "has_unit": True,
            "unit_price": "0.10",
        }]
        bill = {"trade_item_id": "ti-1", "content": "0.1+0.2"}

        self.assertEqual(recompute_bill_total(bill, trade_items, {}), 0.03)

    def test_money_rounding_is_half_up_and_invalid_frozen_values_are_safe(self):
        self.assertEqual(
            recompute_bill_total(
                {"trade_item_id": "ti-2", "content": "1.005"},
                [{"id": "ti-2", "has_unit": False}],
                {},
            ),
            1.01,
        )
        self.assertEqual(recompute_bill_total({"frozen_total": "not-a-number"}, [], {}), 0.0)


if __name__ == "__main__":
    unittest.main()
