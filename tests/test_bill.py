import unittest

from src.bill import Bill


def _bill(**overrides) -> Bill:
    base = {
        "id": "b_abc123",
        "trade_item_id": "ti_1",
        "content": "墙面抹灰",
        "note": "东侧",
        "work_date_type": "单日",
        "work_date_start": "2026-09-01",
        "work_date_end": "2026-09-01",
        "record_time": "2026-09-01 08:00:00",
    }
    base.update(overrides)
    return Bill(**base)


class BillFromDictTests(unittest.TestCase):
    def test_minimal_dict_fills_documented_defaults(self):
        bill = Bill.from_dict({"id": "b_1"})

        self.assertEqual(bill.id, "b_1")
        self.assertEqual(bill.trade_item_id, "")
        self.assertEqual(bill.work_date_type, "无时间")
        self.assertEqual(bill.record_time, "")
        self.assertIsNone(bill.frozen_snapshot)
        self.assertIsNone(bill.frozen_total)
        self.assertFalse(bill.needs_attention)
        self.assertFalse(bill.reviewed)

    def test_legacy_work_date_key_backfills_start(self):
        bill = Bill.from_dict({"work_date": "2026-01-02"})

        self.assertEqual(bill.work_date_start, "2026-01-02")

    def test_explicit_start_wins_over_legacy_work_date(self):
        bill = Bill.from_dict({"work_date_start": "2026-03-03", "work_date": "2026-01-02"})

        self.assertEqual(bill.work_date_start, "2026-03-03")

    def test_underscore_alias_is_normalized_on_load(self):
        # Qt 侧写入的是 _needs_attention，Bill 读的是 needs_attention；
        # 两者都要认，否则标记会在"加载→保存"往返中被静默丢掉。
        self.assertTrue(Bill.from_dict({"_needs_attention": True}).needs_attention)
        self.assertTrue(Bill.from_dict({"needs_attention": True}).needs_attention)
        self.assertFalse(Bill.from_dict({"needs_attention": False, "_needs_attention": False}).needs_attention)

    def test_underscore_alias_survives_dict_round_trip(self):
        bill = Bill.from_dict({"id": "b_1", "_needs_attention": True})

        self.assertIs(bill.to_dict()["needs_attention"], True)


class BillToDictTests(unittest.TestCase):
    def test_optional_keys_are_omitted_when_absent(self):
        payload = _bill().to_dict()

        self.assertNotIn("frozen_snapshot", payload)
        self.assertNotIn("frozen_total", payload)
        self.assertNotIn("needs_attention", payload)

    def test_reviewed_is_always_written_even_when_false(self):
        payload = _bill().to_dict()

        self.assertIn("reviewed", payload)
        self.assertIs(payload["reviewed"], False)

    def test_optional_keys_are_written_when_present(self):
        payload = _bill(
            frozen_snapshot={"name": "抹灰", "unit_price": 12.5},
            frozen_total=250.0,
            needs_attention=True,
            reviewed=True,
        ).to_dict()

        self.assertEqual(payload["frozen_snapshot"], {"name": "抹灰", "unit_price": 12.5})
        self.assertEqual(payload["frozen_total"], 250.0)
        self.assertIs(payload["needs_attention"], True)
        self.assertIs(payload["reviewed"], True)

    def test_round_trip_is_lossless_for_a_fully_populated_bill(self):
        original = _bill(frozen_total=99.5, needs_attention=True, reviewed=True)

        self.assertEqual(Bill.from_dict(original.to_dict()), original)


class BillMappingProtocolTests(unittest.TestCase):
    def test_underscore_alias_reads_needs_attention(self):
        bill = _bill(needs_attention=True)

        self.assertIs(bill.get("_needs_attention"), True)
        self.assertIs(bill["_needs_attention"], True)

    def test_get_falls_back_to_default_for_unknown_key(self):
        self.assertEqual(_bill().get("nope", "fallback"), "fallback")

    def test_contains_reports_frozen_fields_by_presence(self):
        plain = _bill()
        frozen = _bill(frozen_snapshot={}, frozen_total=0.0)

        self.assertNotIn("frozen_snapshot", plain)
        self.assertNotIn("frozen_total", plain)
        self.assertIn("frozen_snapshot", frozen)
        self.assertIn("frozen_total", frozen)

    def test_contains_treats_reviewed_as_always_present(self):
        self.assertIn("reviewed", _bill(reviewed=False))

    def test_contains_reflects_needs_attention_value(self):
        self.assertIn("needs_attention", _bill(needs_attention=True))
        self.assertNotIn("needs_attention", _bill(needs_attention=False))

    def test_setitem_underscore_alias_writes_needs_attention(self):
        bill = _bill()

        bill["_needs_attention"] = 1

        self.assertIs(bill.needs_attention, True)

    def test_update_routes_aliases_and_regular_fields(self):
        bill = _bill()

        bill.update({"_needs_attention": True, "reviewed": True, "content": "改过的内容"})

        self.assertTrue(bill.needs_attention)
        self.assertTrue(bill.reviewed)
        self.assertEqual(bill.content, "改过的内容")


class BillMutationTests(unittest.TestCase):
    def test_pop_returns_frozen_value_and_clears_it(self):
        bill = _bill(frozen_total=42.0)

        self.assertEqual(bill.pop("frozen_total"), 42.0)
        self.assertIsNone(bill.frozen_total)

    def test_pop_returns_default_for_unknown_key_without_clearing(self):
        bill = _bill()

        self.assertEqual(bill.pop("unknown", "d"), "d")
        self.assertEqual(bill.content, "墙面抹灰")

    def test_pop_clears_needs_attention_and_reviewed(self):
        bill = _bill(needs_attention=True, reviewed=True)

        self.assertTrue(bill.pop("needs_attention"))
        self.assertTrue(bill.pop("reviewed"))
        self.assertFalse(bill.needs_attention)
        self.assertFalse(bill.reviewed)

    def test_clear_resets_every_field_to_its_default(self):
        bill = _bill(frozen_snapshot={"x": 1}, frozen_total=1.0, needs_attention=True, reviewed=True)

        bill.clear()

        self.assertEqual(bill, Bill("", "", "", "", "无时间", "", "", ""))


if __name__ == "__main__":
    unittest.main()
