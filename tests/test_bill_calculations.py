import unittest

from src.bill_recompute import prepare_bill_calculations, summarize_bill_calculations
from src.billing_resolver import build_trade_item_index
from src.trade_item import TradeItem


class BillCalculationTests(unittest.TestCase):
    def setUp(self):
        self.trade_items = [
            {
                "id": "ti-1",
                "category": "泥瓦工程",
                "name": "砌墙",
                "has_unit": True,
                "unit_price": "12.50",
                "unit": "㎡",
            }
        ]

    def test_batch_calculation_reuses_one_display_result(self):
        bills = [
            {"trade_item_id": "ti-1", "content": "2+1"},
            {"trade_item_id": "ti-1", "content": "bad"},
        ]

        calculations, total, errors = summarize_bill_calculations(
            bills, self.trade_items, {}
        )

        self.assertEqual(len(calculations), 2)
        self.assertEqual(calculations[0].canonical, "2+1")
        self.assertEqual(calculations[0].formula_value, 3)
        self.assertEqual(calculations[0].total, 37.50)
        self.assertTrue(calculations[1].formula_error)
        self.assertEqual(total, 37.50)
        self.assertEqual(errors, 1)

    def test_orphan_uses_frozen_snapshot_and_frozen_total(self):
        bill = {
            "trade_item_id": "",
            "content": "2+2",
            "frozen_total": "88.005",
            "frozen_snapshot": {
                "category": "已删除",
                "name": "旧项目",
                "has_unit": True,
                "unit_price": 1,
                "unit": "项",
            },
        }

        result = prepare_bill_calculations([bill], self.trade_items, {})[0]

        self.assertTrue(result.orphan)
        self.assertEqual(result.name, "旧项目")
        self.assertEqual(result.total, 88.01)
        self.assertEqual(result.formula_value, 4)

    def test_trade_item_object_provides_work_content_label(self):
        trade_item = TradeItem.from_dict(self.trade_items[0])

        result = prepare_bill_calculations(
            [{"trade_item_id": "ti-1", "content": "2"}],
            [trade_item],
            {},
        )[0]

        self.assertFalse(result.orphan)
        self.assertEqual(result.category, "泥瓦工程")
        self.assertEqual(result.name, "砌墙")
        self.assertEqual(result.total, 25.00)

    def test_index_keeps_first_duplicate_id(self):
        first = {"id": "same", "name": "first"}
        second = {"id": "same", "name": "second"}

        index = build_trade_item_index([first, second])

        self.assertIs(index["same"], first)


if __name__ == "__main__":
    unittest.main()
