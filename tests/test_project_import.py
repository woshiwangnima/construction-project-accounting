import json
import os
import tempfile
import unittest
from pathlib import Path

from src import project_manager as pm


class ProjectImportTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        root = Path(self._tmp.name)
        self.projects_dir = root / "projects"
        self.backups_dir = root / "backups"
        self._old_projects_dir = os.environ.get("CPA_PROJECTS_DIR")
        self._old_backups_dir = os.environ.get("CPA_BACKUPS_DIR")
        os.environ["CPA_PROJECTS_DIR"] = str(self.projects_dir)
        os.environ["CPA_BACKUPS_DIR"] = str(self.backups_dir)
        pm._invalidate_list_cache()

    def tearDown(self):
        if self._old_projects_dir is None:
            os.environ.pop("CPA_PROJECTS_DIR", None)
        else:
            os.environ["CPA_PROJECTS_DIR"] = self._old_projects_dir
        if self._old_backups_dir is None:
            os.environ.pop("CPA_BACKUPS_DIR", None)
        else:
            os.environ["CPA_BACKUPS_DIR"] = self._old_backups_dir
        pm._invalidate_list_cache()
        self._tmp.cleanup()

    def test_import_preserves_complete_project_and_generates_new_uuid(self):
        source = {
            "project_uuid": "11111111-1111-1111-1111-111111111111",
            "name": "导入测试项目",
            "status": "done",
            "created_at": "2026-01-01",
            "last_modified": "2026-01-02 10:00:00",
            "description": "项目说明",
            "project_date_type": "单个时间",
            "project_date_start": "2026-01-01",
            "project_date_end": "",
            "category_order": [{"id": "cat_test", "name": "装饰工程"}],
            "trade_items": [{
                "id": "ti_test",
                "category_id": "cat_test",
                "name": "墙面施工",
                "has_unit": True,
                "unit_price": 100,
                "unit": "㎡",
            }],
            "bills": [{
                "id": "bill_test",
                "trade_item_id": "ti_test",
                "content": "2*3",
                "note": "导入账单",
                "work_date_type": "无时间",
                "work_date_start": "",
                "work_date_end": "",
                "record_time": "2026-01-02 10:00:00",
                "reviewed": True,
            }],
            "bill_column_widths": [{"name": "公式", "weight": 0.2}],
            "worker_column_widths": {"名称": 0.5},
            "view_state": {"lists": {"bills": {"item_id": "bill_test"}}},
            "bill_display_mode": "simple",
            "is_pinned": True,
            "schema_version": 1,
        }
        input_path = Path(self._tmp.name) / "export.json"
        input_path.write_text(json.dumps(source, ensure_ascii=False), encoding="utf-8")

        imported = pm.import_project(str(input_path))
        stored = pm.get_project(imported.project_uuid)

        self.assertNotEqual(imported.project_uuid, source["project_uuid"])
        self.assertEqual(stored.name, source["name"])
        self.assertEqual(stored.description, source["description"])
        self.assertEqual(stored.status, "done")
        self.assertEqual(len(stored.trade_items), 1)
        self.assertEqual(len(stored.bills), 1)
        self.assertEqual(stored.bills[0].note, "导入账单")
        self.assertEqual(stored.bill_column_widths, source["bill_column_widths"])
        self.assertEqual(stored.worker_column_widths, source["worker_column_widths"])
        self.assertEqual(stored.view_state, source["view_state"])
        self.assertEqual(stored.bill_display_mode, "simple")
        self.assertTrue(stored.is_pinned)

    def test_import_rejects_non_object_json(self):
        input_path = Path(self._tmp.name) / "invalid.json"
        input_path.write_text("[]", encoding="utf-8")

        with self.assertRaises(ValueError):
            pm.import_project(str(input_path))


if __name__ == "__main__":
    unittest.main()
