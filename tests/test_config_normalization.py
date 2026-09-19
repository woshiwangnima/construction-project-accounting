import copy
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from src import config_loader
from src.config_normalization import merge_defaults
from src.utils import atomic_write_json


class ConfigNormalizationTests(unittest.TestCase):
    def test_new_fields_follow_names_preserving_order_and_preferences(self):
        defaults = {"columns": [
            {"name": "amount", "width": 10, "display": {"audit": True, "simple": False}},
            {"name": "note", "width": 20, "display": {"audit": False}},
            {"name": "removed", "width": 30},
        ]}
        legacy = {"columns": [
            {"name": "note", "width": 80},
            {"name": "custom", "extension": {"visible": True}},
            {"name": "amount", "display": {"audit": False}},
        ], "extension": {"enabled": True}}

        merged = merge_defaults(defaults, legacy)

        self.assertEqual([row["name"] for row in merged["columns"]],
                         ["note", "custom", "amount"])
        self.assertEqual(merged["columns"][0], {
            "name": "note", "width": 80, "display": {"audit": False},
        })
        self.assertEqual(merged["columns"][2]["display"], {"audit": False, "simple": False})
        self.assertEqual(merged["columns"][1], legacy["columns"][1])
        self.assertEqual(merged["extension"], legacy["extension"])

    def test_ordinary_and_explicitly_empty_lists_are_replaced(self):
        self.assertEqual(merge_defaults({
            "size": [900, 700], "columns": [{"name": "a", "visible": True}],
            "notes": [{"version": "2", "notes": ["new"]}],
        }, {
            "size": [300, 200], "columns": [], "notes": [{"version": "1"}],
        }), {
            "size": [300, 200], "columns": [], "notes": [{"version": "1"}],
        })

    def test_unknown_or_malformed_rows_are_preserved_without_aliasing(self):
        defaults = {"columns": [{"name": "a", "options": {"visible": True}}]}
        values = {"columns": ["legacy", {"name": ["unexpected"]}, {"name": "a"}],
                  "custom": {"values": [1]}}
        original_defaults, original_values = copy.deepcopy((defaults, values))

        merged = merge_defaults(defaults, values)
        self.assertEqual(merged["columns"][:2], values["columns"][:2])
        merged["columns"][1]["name"].append("modified")
        merged["columns"][2]["options"]["visible"] = False
        merged["custom"]["values"].append(2)

        self.assertEqual(defaults, original_defaults)
        self.assertEqual(values, original_values)

    def test_nested_named_lists_receive_future_flags(self):
        self.assertEqual(merge_defaults(
            {"pages": [{"name": "bill", "columns": [{"name": "amount", "future_flag": True}]}]},
            {"pages": [{"name": "bill", "columns": [{"name": "amount", "width": 8}]}]},
        )["pages"][0]["columns"], [{"name": "amount", "future_flag": True, "width": 8}])


class AppConfigCacheTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.config_dir = self.root / "config"
        self.resources = self.root / "resources"
        self.resources.mkdir()
        self.resource_path = self.resources / "app_config.json"
        self.resource_path.write_text('{"probe": "bundled"}', encoding="utf-8")
        for patcher in (
            patch.dict(os.environ, {"CPA_CONFIG_DIR": str(self.config_dir)}),
            patch.object(config_loader, "get_resource_config_dir", return_value=self.resources),
            patch.object(config_loader, "_app_cache", None),
            patch.object(config_loader, "_app_cache_key", None),
        ):
            patcher.start()
            self.addCleanup(patcher.stop)

    def test_configuration_directory_change_does_not_reuse_previous_cache(self):
        config_loader.save_app({"probe": "first"})
        self.assertEqual(config_loader.load_app()["probe"], "first")
        second_dir = self.root / "second"
        atomic_write_json(str(second_dir / "app_config.json"), {"probe": "second"})

        with patch.dict(os.environ, {"CPA_CONFIG_DIR": str(second_dir)}):
            self.assertEqual(config_loader.load_app()["probe"], "second")

        self.assertEqual(config_loader.load_app()["probe"], "first")

    def test_external_atomic_replacement_invalidates_cache(self):
        config_loader.save_app({"probe": "first"})
        self.assertEqual(config_loader.load_app()["probe"], "first")
        atomic_write_json(str(self.config_dir / "app_config.json"), {"probe": "external"})
        self.assertEqual(config_loader.load_app()["probe"], "external")

    def test_create_and_remove_user_file_updates_bundled_fallback(self):
        self.assertEqual(config_loader.load_app()["probe"], "bundled")
        user_path = self.config_dir / "app_config.json"
        atomic_write_json(str(user_path), {"probe": "user"})
        self.assertEqual(config_loader.load_app()["probe"], "user")
        user_path.unlink()
        self.assertEqual(config_loader.load_app()["probe"], "bundled")

    def test_bundled_fallback_change_invalidates_cache(self):
        self.assertEqual(config_loader.load_app()["probe"], "bundled")
        atomic_write_json(str(self.resource_path), {"probe": "new bundled"})
        self.assertEqual(config_loader.load_app()["probe"], "new bundled")

    def test_unchanged_file_is_not_parsed_twice_and_returned_values_are_independent(self):
        with patch.object(config_loader, "load_json", wraps=config_loader.load_json) as read:
            first = config_loader.load_app()
            first["window_sizes"]["settings"] = [1, 2]
            second = config_loader.load_app()
        self.assertEqual(read.call_count, 1)
        self.assertNotEqual(second["window_sizes"]["settings"], [1, 2])

    def test_load_normalizes_columns_without_writing_until_explicit_save(self):
        legacy = {"default_bill_column_widths_data": [
            {"name": "#", "weight": 0.8, "show_in_audit": True},
            {"name": "custom", "extension": 42},
        ], "extension": {"keep": True}}
        user_path = self.config_dir / "app_config.json"
        atomic_write_json(str(user_path), legacy)

        loaded = config_loader.load_app()

        self.assertTrue(loaded["default_bill_column_widths_data"][0]["show_in_simple"])
        self.assertTrue(loaded["default_bill_column_widths_data"][0]["show_in_audit"])
        self.assertEqual(json.loads(user_path.read_text(encoding="utf-8")), legacy)
        config_loader.save_app(loaded)
        self.assertEqual(config_loader.load_app(), loaded)
        self.assertEqual(json.loads(user_path.read_text(encoding="utf-8")), loaded)


if __name__ == "__main__":
    unittest.main()
