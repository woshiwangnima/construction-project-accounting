import copy
import unittest

from src.paste_actions import (
    paste_bill,
    paste_trade_item,
    unique_category_after_paste,
)
from src.trade_item_id import compute_bill_id


TRADE_ITEMS = [
    {"id": "ti_aaa", "name": "抹灰", "has_unit": True, "unit_price": 12.0, "unit": "m²"},
    {"id": "ti_bbb", "name": "砌墙", "has_unit": True, "unit_price": 80.0, "unit": "m³"},
]

NOW = "2026-09-18 10:00:00"


class PasteBillLinkedTests(unittest.TestCase):
    def test_matching_trade_item_is_kept_and_bill_is_not_flagged(self):
        payload = {"content": "3*12", "trade_item_id": "ti_aaa"}

        new_bill = paste_bill(payload, TRADE_ITEMS, now=NOW)

        self.assertEqual(new_bill["trade_item_id"], "ti_aaa")
        self.assertNotIn("_needs_attention", new_bill)
        self.assertNotIn("frozen_snapshot", new_bill)

    def test_bill_id_is_derived_from_the_resolved_association(self):
        payload = {"content": "3*12", "trade_item_id": "ti_aaa"}

        new_bill = paste_bill(payload, TRADE_ITEMS, now=NOW)

        self.assertEqual(new_bill["id"], compute_bill_id("ti_aaa", "3*12", NOW))

    def test_record_time_falls_back_to_now_when_not_injected(self):
        new_bill = paste_bill({"content": "1", "trade_item_id": "ti_aaa"}, TRADE_ITEMS)

        self.assertTrue(new_bill["record_time"])

    def test_note_is_only_written_when_present(self):
        with_note = paste_bill({"content": "1", "trade_item_id": "ti_aaa", "note": "东侧"}, TRADE_ITEMS, now=NOW)
        without_note = paste_bill({"content": "1", "trade_item_id": "ti_aaa", "note": ""}, TRADE_ITEMS, now=NOW)

        self.assertEqual(with_note["note"], "东侧")
        self.assertNotIn("note", without_note)

    def test_legacy_work_date_backfills_start(self):
        new_bill = paste_bill(
            {"content": "1", "trade_item_id": "ti_aaa", "work_date": "2026-01-02"},
            TRADE_ITEMS,
            now=NOW,
        )

        self.assertEqual(new_bill["work_date_start"], "2026-01-02")

    def test_default_date_type_is_untimed(self):
        new_bill = paste_bill({"content": "1", "trade_item_id": "ti_aaa"}, TRADE_ITEMS, now=NOW)

        self.assertEqual(new_bill["work_date_type"], "无时间")


class PasteBillOrphanTests(unittest.TestCase):
    def test_unknown_trade_item_becomes_orphan_with_attention_flag(self):
        payload = {"content": "5*5", "trade_item_id": "ti_missing", "frozen_total": 25.0}

        new_bill = paste_bill(payload, TRADE_ITEMS, now=NOW)

        self.assertEqual(new_bill["trade_item_id"], "")
        self.assertIs(new_bill["_needs_attention"], True)
        self.assertEqual(new_bill["frozen_total"], 25.0)

    def test_orphan_id_uses_reserved_placeholder(self):
        payload = {"content": "5*5", "trade_item_id": "ti_missing"}

        new_bill = paste_bill(payload, TRADE_ITEMS, now=NOW)

        self.assertEqual(new_bill["id"], compute_bill_id("", "5*5", NOW))

    def test_payload_without_trade_item_id_pastes_as_orphan(self):
        new_bill = paste_bill({"content": "5*5"}, TRADE_ITEMS, now=NOW)

        self.assertEqual(new_bill["trade_item_id"], "")
        self.assertIs(new_bill["_needs_attention"], True)

    def test_frozen_snapshot_is_deep_copied_not_shared(self):
        snapshot = {"name": "抹灰", "unit_price": 12.0, "nested": {"unit": "m²"}}
        payload = {"content": "1", "trade_item_id": "ti_missing", "frozen_snapshot": snapshot}

        new_bill = paste_bill(payload, TRADE_ITEMS, now=NOW)
        new_bill["frozen_snapshot"]["nested"]["unit"] = "改了"

        self.assertEqual(snapshot["nested"]["unit"], "m²")
        self.assertIsNot(new_bill["frozen_snapshot"], snapshot)

    def test_empty_trade_items_always_orphans(self):
        new_bill = paste_bill({"content": "1", "trade_item_id": "ti_aaa"}, [], now=NOW)

        self.assertEqual(new_bill["trade_item_id"], "")
        self.assertIs(new_bill["_needs_attention"], True)

    def test_missing_frozen_total_is_not_invented(self):
        new_bill = paste_bill({"content": "1", "trade_item_id": "ti_missing"}, TRADE_ITEMS, now=NOW)

        self.assertNotIn("frozen_total", new_bill)


class PasteBillImmutabilityTests(unittest.TestCase):
    def test_payload_and_target_items_are_not_mutated(self):
        payload = {"content": "3*12", "trade_item_id": "ti_aaa", "note": "东侧"}
        items = copy.deepcopy(TRADE_ITEMS)

        paste_bill(payload, items, now=NOW)

        self.assertEqual(payload, {"content": "3*12", "trade_item_id": "ti_aaa", "note": "东侧"})
        self.assertEqual(items, TRADE_ITEMS)


class PasteTradeItemTests(unittest.TestCase):
    def test_new_id_is_generated_and_never_reuses_the_source(self):
        payload = {"category": "泥瓦", "name": "抹灰", "has_unit": True, "unit_price": 12.0, "unit": "m²"}

        new_ti = paste_trade_item(payload, TRADE_ITEMS)

        self.assertTrue(new_ti.id.startswith("ti_"))
        self.assertNotIn(new_ti.id, {"ti_aaa", "ti_bbb"})

    def test_conflicting_name_gets_copy_suffix(self):
        payload = {"category": "泥瓦", "name": "抹灰", "has_unit": True, "unit_price": 12.0, "unit": "m²"}

        self.assertEqual(paste_trade_item(payload, TRADE_ITEMS).name, "抹灰 副本")

    def test_repeated_copy_suffix_keeps_incrementing(self):
        existing = [
            {"id": "ti_1", "name": "抹灰"},
            {"id": "ti_2", "name": "抹灰 副本"},
            {"id": "ti_3", "name": "抹灰 副本 2"},
        ]
        payload = {"category": "泥瓦", "name": "抹灰", "has_unit": True, "unit_price": 12.0, "unit": "m²"}

        self.assertEqual(paste_trade_item(payload, existing).name, "抹灰 副本 3")

    def test_non_conflicting_name_is_kept_as_is(self):
        payload = {"category": "泥瓦", "name": "刷漆", "has_unit": True, "unit_price": 12.0, "unit": "m²"}

        self.assertEqual(paste_trade_item(payload, TRADE_ITEMS).name, "刷漆")

    def test_category_id_resolves_from_category_objects(self):
        class _Cat:
            def __init__(self, id, name):
                self.id = id
                self.name = name

        payload = {"category": "泥瓦", "name": "刷漆", "has_unit": True, "unit_price": 1.0, "unit": ""}

        new_ti = paste_trade_item(payload, TRADE_ITEMS, [_Cat("cat_1", "泥瓦")])

        self.assertEqual(new_ti.category_id, "cat_1")
        self.assertEqual(new_ti.category, "泥瓦")

    def test_category_id_is_empty_when_category_is_not_in_target_order(self):
        payload = {"category": "水电", "name": "走线", "has_unit": True, "unit_price": 1.0, "unit": ""}

        new_ti = paste_trade_item(payload, TRADE_ITEMS, ["泥瓦"])

        self.assertEqual(new_ti.category_id, "")

    def test_disabled_unit_paste_zeroes_price_and_unit(self):
        payload = {"category": "泥瓦", "name": "包工", "has_unit": False, "unit_price": 999.0, "unit": "个"}

        new_ti = paste_trade_item(payload, TRADE_ITEMS)

        self.assertFalse(new_ti.has_unit)
        self.assertEqual(new_ti.unit_price, 0)
        self.assertEqual(new_ti.unit, "")

    def test_result_is_serializable_to_the_flat_dict_schema(self):
        payload = {"category": "泥瓦", "name": "刷漆", "has_unit": True, "unit_price": 3.5, "unit": "m²"}

        dumped = paste_trade_item(payload, TRADE_ITEMS).to_dict()

        self.assertEqual(
            set(dumped),
            {"id", "category_id", "name", "has_unit", "unit_price", "unit"},
        )
        self.assertEqual(dumped["unit_price"], 3.5)


class UniqueCategoryAfterPasteTests(unittest.TestCase):
    def test_new_category_needs_to_be_appended(self):
        self.assertTrue(unique_category_after_paste("水电", ["泥瓦", "木工"]))

    def test_existing_category_is_not_duplicated(self):
        self.assertFalse(unique_category_after_paste("泥瓦", ["泥瓦", "木工"]))

    def test_category_objects_are_compared_by_name(self):
        class _Cat:
            def __init__(self, name):
                self.name = name

        self.assertFalse(unique_category_after_paste("泥瓦", [_Cat("泥瓦")]))


if __name__ == "__main__":
    unittest.main()
