import json
import os
import tempfile
import unittest
from pathlib import Path

from src.migrate_v3 import _gen_bill_id, _migrate_one


class _MigrateCase(unittest.TestCase):
    """给 _migrate_one 准备一个临时项目目录。"""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.projects_dir = Path(self._tmp.name) / "projects"
        self.backups_dir = Path(self._tmp.name) / "backups"
        self.projects_dir.mkdir()

    def write_project(self, doc: dict, name: str = "p1.json") -> str:
        path = self.projects_dir / name
        path.write_text(json.dumps(doc, ensure_ascii=False), encoding="utf-8")
        return str(path)

    def migrate(self, doc: dict, dry_run: bool = False) -> tuple[dict, str]:
        """写入项目文件并迁移，默认执行真实迁移（便于回读结果）。"""
        path = self.write_project(doc)
        report = _migrate_one(path, dry_run, str(self.backups_dir))
        return report, path

    def read(self, path: str) -> dict:
        return json.loads(Path(path).read_text(encoding="utf-8"))


class MigrateCategoriesTests(_MigrateCase):
    def test_legacy_string_categories_become_id_name_objects(self):
        _, path = self.migrate({"category_order": ["泥瓦", "木工"]})

        migrated = self.read(path)["category_order"]

        self.assertEqual([c["name"] for c in migrated], ["泥瓦", "木工"])
        self.assertTrue(all(c["id"].startswith("cat_") for c in migrated))

    def test_duplicate_legacy_category_names_share_one_id(self):
        _, path = self.migrate({"category_order": ["泥瓦", "泥瓦", "木工"]})

        migrated = self.read(path)["category_order"]

        self.assertEqual(len(migrated), 3)
        self.assertEqual(migrated[0]["id"], migrated[1]["id"])
        self.assertNotEqual(migrated[0]["id"], migrated[2]["id"])

    def test_existing_dict_categories_keep_their_ids(self):
        doc = {"category_order": [{"id": "cat_keep", "name": "泥瓦"}]}

        _, path = self.migrate(doc)

        self.assertEqual(self.read(path)["category_order"], [{"id": "cat_keep", "name": "泥瓦"}])

    def test_dict_category_without_id_gets_one_generated(self):
        _, path = self.migrate({"category_order": [{"name": "泥瓦"}]})

        self.assertTrue(self.read(path)["category_order"][0]["id"].startswith("cat_"))

    def test_empty_category_order_stays_empty(self):
        report, path = self.migrate({"category_order": []})

        self.assertEqual(self.read(path)["category_order"], [])
        self.assertEqual(report["categories"], 0)


class MigrateTradeItemTests(_MigrateCase):
    def test_v3_trade_item_keeps_its_id(self):
        doc = {"trade_items": [{"id": "ti_keep", "category_id": "cat_1", "name": "抹灰"}]}

        _, path = self.migrate(doc)

        self.assertEqual(self.read(path)["trade_items"][0]["id"], "ti_keep")

    def test_legacy_trade_item_gets_a_fresh_id(self):
        doc = {"trade_items": [{"category": "泥瓦", "name": "抹灰"}]}

        _, path = self.migrate(doc)

        migrated = self.read(path)["trade_items"][0]
        self.assertTrue(migrated["id"].startswith("ti_"))
        self.assertEqual(migrated["name"], "抹灰")

    def test_legacy_category_name_resolves_to_the_generated_category_id(self):
        doc = {
            "category_order": ["泥瓦"],
            "trade_items": [{"category": "泥瓦", "name": "抹灰"}],
        }

        _, path = self.migrate(doc)

        migrated = self.read(path)
        self.assertEqual(migrated["trade_items"][0]["category_id"], migrated["category_order"][0]["id"])

    def test_v3_category_id_resolves_back_to_its_category_name(self):
        doc = {
            "category_order": [{"id": "cat_1", "name": "泥瓦"}],
            "trade_items": [{"id": "ti_1", "category_id": "cat_1", "name": "抹灰"}],
        }

        _, path = self.migrate(doc)

        self.assertEqual(self.read(path)["trade_items"][0]["category_id"], "cat_1")

    def test_unknown_category_leaves_category_id_empty(self):
        doc = {"trade_items": [{"category": "水电", "name": "走线"}]}

        _, path = self.migrate(doc)

        self.assertEqual(self.read(path)["trade_items"][0]["category_id"], "")

    def test_billing_fields_are_normalized_to_the_flat_schema(self):
        doc = {"trade_items": [{"category": "泥瓦", "name": "抹灰", "has_unit": False, "unit_price": 99}]}

        _, path = self.migrate(doc)

        migrated = self.read(path)["trade_items"][0]
        self.assertEqual(set(migrated), {"id", "category_id", "name", "has_unit", "unit_price", "unit"})
        self.assertIs(migrated["has_unit"], False)
        self.assertEqual(migrated["unit_price"], 99.0)
        self.assertEqual(migrated["unit"], "")

    def test_billing_defaults_are_applied_when_fields_are_missing(self):
        doc = {"trade_items": [{"category": "泥瓦", "name": "抹灰"}]}

        _, path = self.migrate(doc)

        migrated = self.read(path)["trade_items"][0]
        self.assertIs(migrated["has_unit"], True)
        self.assertEqual(migrated["unit_price"], 1.0)


class MigrateBillAssociationTests(_MigrateCase):
    def test_bill_follows_its_trade_item_when_the_id_is_remapped(self):
        doc = {
            "category_order": ["泥瓦"],
            "trade_items": [{"id": "old_ti", "category": "泥瓦", "name": "抹灰"}],
            "bills": [{"trade_item_id": "old_ti", "content": "1*2", "record_time": "2026-01-01"}],
        }

        _, path = self.migrate(doc)

        migrated = self.read(path)
        self.assertEqual(migrated["bills"][0]["trade_item_id"], migrated["trade_items"][0]["id"])

    def test_bill_kept_by_v3_id_needs_no_remap(self):
        doc = {
            "trade_items": [{"id": "ti_1", "category_id": "cat_1", "name": "抹灰"}],
            "bills": [{"trade_item_id": "ti_1", "content": "1*2"}],
        }

        _, path = self.migrate(doc)

        self.assertEqual(self.read(path)["bills"][0]["trade_item_id"], "ti_1")

    def test_unknown_trade_item_id_yields_an_orphan(self):
        doc = {"trade_items": [], "bills": [{"trade_item_id": "ti_gone", "content": "1*2"}]}

        report, path = self.migrate(doc)

        self.assertEqual(self.read(path)["bills"][0]["trade_item_id"], "")
        self.assertEqual(report["orphans"], 1)

    def test_bill_with_empty_trade_item_id_is_an_orphan_not_attached_to_an_idless_item(self):
        # 回归：旧文件里缺 id 的工作项会占用 "" 这个键，
        # 曾在迁移时把真正的孤儿账单静默挂到那个工作项上。
        doc = {
            "category_order": ["泥瓦"],
            "trade_items": [{"category": "泥瓦", "name": "抹灰"}],
            "bills": [{"trade_item_id": "", "content": "无归属历史账单", "record_time": "2026-01-01"}],
        }

        report, path = self.migrate(doc)

        self.assertEqual(self.read(path)["bills"][0]["trade_item_id"], "")
        self.assertEqual(report["orphans"], 1)

    def test_orphan_bill_with_frozen_snapshot_is_flagged_for_attention(self):
        doc = {
            "bills": [{
                "trade_item_id": "ti_gone",
                "content": "1*2",
                "frozen_snapshot": {"name": "抹灰", "unit_price": 12.0},
            }],
        }

        _, path = self.migrate(doc)

        self.assertIs(self.read(path)["bills"][0]["needs_attention"], True)

    def test_linked_bill_is_not_flagged(self):
        doc = {
            "trade_items": [{"id": "ti_1", "category_id": "cat_1", "name": "抹灰"}],
            "bills": [{"trade_item_id": "ti_1", "content": "1*2", "frozen_snapshot": {"name": "x"}}],
        }

        _, path = self.migrate(doc)

        self.assertNotIn("needs_attention", self.read(path)["bills"][0])

    def test_underscore_attention_flag_is_normalized_to_the_schema_key(self):
        doc = {"bills": [{"trade_item_id": "", "content": "1", "_needs_attention": True}]}

        _, path = self.migrate(doc)

        self.assertIs(self.read(path)["bills"][0]["needs_attention"], True)

    def test_bill_id_is_recomputed_stably(self):
        doc = {
            "trade_items": [{"id": "ti_1", "category_id": "cat_1", "name": "抹灰"}],
            "bills": [{"trade_item_id": "ti_1", "content": "1*2", "record_time": "2026-01-01"}],
        }

        _, path = self.migrate(doc)

        self.assertEqual(
            self.read(path)["bills"][0]["id"],
            _gen_bill_id("ti_1", "1*2", "2026-01-01"),
        )

    def test_legacy_work_date_backfills_start(self):
        doc = {"bills": [{"trade_item_id": "", "content": "1", "work_date": "2026-02-03"}]}

        _, path = self.migrate(doc)

        self.assertEqual(self.read(path)["bills"][0]["work_date_start"], "2026-02-03")

    def test_default_date_type_is_untimed(self):
        doc = {"bills": [{"trade_item_id": "", "content": "1"}]}

        _, path = self.migrate(doc)

        self.assertEqual(self.read(path)["bills"][0]["work_date_type"], "无时间")

    def test_absent_frozen_fields_are_not_invented(self):
        doc = {"bills": [{"trade_item_id": "", "content": "1"}]}

        _, path = self.migrate(doc)

        migrated = self.read(path)["bills"][0]
        self.assertNotIn("frozen_snapshot", migrated)
        self.assertNotIn("frozen_total", migrated)

    def test_frozen_total_zero_is_preserved(self):
        doc = {"bills": [{"trade_item_id": "", "content": "1", "frozen_total": 0.0}]}

        _, path = self.migrate(doc)

        self.assertEqual(self.read(path)["bills"][0]["frozen_total"], 0.0)


class MigrateMetadataAndIoTests(_MigrateCase):
    def test_internal_migration_keys_are_stripped(self):
        doc = {
            "category_order": [],
            "trade_items": [],
            "bills": [],
            "_migrated_v2": True,
            "_migrated_v3": True,
            "_path": "/old/path.json",
            "_needs_attention": True,
        }

        _, path = self.migrate(doc)

        migrated = self.read(path)
        for key in ("_migrated_v2", "_migrated_v3", "_path", "_needs_attention"):
            self.assertNotIn(key, migrated)

    def test_dry_run_leaves_the_file_untouched_and_writes_no_backup(self):
        doc = {"category_order": ["泥瓦"], "trade_items": [], "bills": []}
        path = self.write_project(doc)
        before = Path(path).read_bytes()

        _migrate_one(path, True, str(self.backups_dir))

        self.assertEqual(Path(path).read_bytes(), before)
        self.assertFalse(self.backups_dir.exists())

    def test_real_run_rewrites_the_file_and_creates_one_backup(self):
        doc = {"project_uuid": "p1", "category_order": ["泥瓦"], "trade_items": [], "bills": []}
        path = self.write_project(doc)
        before = self.read(path)

        _migrate_one(path, False, str(self.backups_dir))

        self.assertNotEqual(self.read(path)["category_order"], before["category_order"])
        backups = list(self.backups_dir.glob("p_p1_*.json"))
        self.assertEqual(len(backups), 1)
        self.assertEqual(json.loads(backups[0].read_text(encoding="utf-8")), before)

    def test_backup_name_falls_back_to_the_file_stem_without_a_uuid(self):
        doc = {"category_order": ["泥瓦"], "trade_items": [], "bills": []}
        path = self.write_project(doc, name="naked.json")

        _migrate_one(path, False, str(self.backups_dir))

        self.assertEqual(len(list(self.backups_dir.glob("p_naked_*.json"))), 1)

    def test_no_temp_file_is_left_behind_after_the_atomic_write(self):
        path = self.write_project({"category_order": ["泥瓦"]})

        _migrate_one(path, False, str(self.backups_dir))

        self.assertFalse(os.path.exists(path + ".tmp"))

    def test_report_counts_match_the_migrated_document(self):
        doc = {
            "category_order": ["泥瓦", "木工"],
            "trade_items": [{"category": "泥瓦", "name": "抹灰"}, {"category": "木工", "name": "吊顶"}],
            "bills": [
                {"trade_item_id": "ti_gone", "content": "1"},
                {"trade_item_id": "", "content": "2"},
                {"trade_item_id": "ti_also_gone", "content": "3"},
            ],
        }

        report, _ = self.migrate(doc)

        self.assertEqual(
            {k: report[k] for k in ("categories", "trade_items", "bills", "orphans", "status")},
            {"categories": 2, "trade_items": 2, "bills": 3, "orphans": 3, "status": "ok"},
        )


if __name__ == "__main__":
    unittest.main()
