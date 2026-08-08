import json
import os
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from src.backup_policy import (
    list_backup_paths,
    next_sequence_backup_path,
    rotate_sequence_backups,
)
from src.config_loader import load_user, load_app, save_app
from src.project_manager import _backup_project, _safe_path
from src.single_instance import SingleInstanceLock
from src.utils import atomic_write_json
from src.versioning import migrate_json_file, rollback_migration_batch


class StorageSafetyTests(unittest.TestCase):
    def test_path_guard_rejects_sibling_prefix(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp) / "projects"
            base.mkdir()
            with self.assertRaises(ValueError):
                _safe_path(str(base), "..\\projects_evil\\project.json")

    def test_atomic_write_keeps_target_when_replace_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "project.json"
            target.write_text('{"old": true}', encoding="utf-8")

            with patch("src.utils.os.replace", side_effect=OSError("locked")):
                with self.assertRaises(OSError):
                    atomic_write_json(str(target), {"new": True}, max_retries=1)

            self.assertEqual(json.loads(target.read_text(encoding="utf-8")), {"old": True})
            self.assertEqual(list(Path(tmp).glob(".tmp_*.json.tmp")), [])

    def test_user_defaults_are_not_shared_between_loads(self):
        with tempfile.TemporaryDirectory() as tmp:
            old_config = os.environ.get("CPA_CONFIG_DIR")
            os.environ["CPA_CONFIG_DIR"] = tmp
            try:
                first = load_user()
                first.setdefault("window_sizes", {})["settings"] = [1, 2]
                second = load_user()
                self.assertNotEqual(second.get("window_sizes", {}).get("settings"), [1, 2])
            finally:
                if old_config is None:
                    os.environ.pop("CPA_CONFIG_DIR", None)
                else:
                    os.environ["CPA_CONFIG_DIR"] = old_config

    def test_save_app_invalidates_cached_load(self):
        with tempfile.TemporaryDirectory() as tmp:
            old_config = os.environ.get("CPA_CONFIG_DIR")
            os.environ["CPA_CONFIG_DIR"] = tmp
            try:
                before = load_app()
                self.assertNotIn("test_probe", before)
                cfg = load_app()
                cfg["test_probe"] = 42
                save_app(cfg)
                after = load_app()
                self.assertEqual(after.get("test_probe"), 42)
            finally:
                if old_config is None:
                    os.environ.pop("CPA_CONFIG_DIR", None)
                else:
                    os.environ["CPA_CONFIG_DIR"] = old_config

    def test_backup_retention_includes_legacy_files_and_orders_by_mtime(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            project = root / "p_demo.json"
            backups = root / "backups"
            backups.mkdir()
            old = backups / "p_demo_20240101_010101.json"
            middle = backups / "p_demo.1.json"
            newest = backups / "p_demo.2.json"
            for index, path in enumerate((old, middle, newest), start=1):
                path.write_text(str(index), encoding="utf-8")
                os.utime(path, (index, index))

            rotate_sequence_backups(project, backups, 2)
            remaining = list_backup_paths("demo", backups)

            self.assertEqual([p.name for p in remaining], [newest.name, middle.name])
            self.assertEqual(next_sequence_backup_path(project, backups).name, "p_demo.3.json")

    def test_project_backup_rotates_after_atomic_copy(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            projects = root / "projects"
            backups = root / "backups"
            projects.mkdir()
            backups.mkdir()
            project_uuid = "11111111-1111-1111-1111-111111111111"
            source = projects / f"p_{project_uuid}.json"
            unrelated = backups / f"p_{project_uuid}_notes.json"
            unrelated.write_text("keep", encoding="utf-8")

            old_projects = os.environ.get("CPA_PROJECTS_DIR")
            old_backups = os.environ.get("CPA_BACKUPS_DIR")
            os.environ["CPA_PROJECTS_DIR"] = str(projects)
            os.environ["CPA_BACKUPS_DIR"] = str(backups)
            try:
                with patch("src.project_manager._get_backup_count", return_value=2):
                    for value in (1, 2, 3):
                        source.write_text(json.dumps({"value": value}), encoding="utf-8")
                        _backup_project(project_uuid, force=True)
                        time.sleep(0.002)
            finally:
                if old_projects is None:
                    os.environ.pop("CPA_PROJECTS_DIR", None)
                else:
                    os.environ["CPA_PROJECTS_DIR"] = old_projects
                if old_backups is None:
                    os.environ.pop("CPA_BACKUPS_DIR", None)
                else:
                    os.environ["CPA_BACKUPS_DIR"] = old_backups

            sequence_backups = sorted(backups.glob(f"p_{project_uuid}.*.json"))
            self.assertEqual([p.name for p in sequence_backups], [
                f"p_{project_uuid}.2.json",
                f"p_{project_uuid}.3.json",
            ])
            self.assertTrue(unrelated.exists())
            self.assertEqual(json.loads(sequence_backups[-1].read_text(encoding="utf-8")), {"value": 3})

    def test_single_instance_lock_can_be_released_and_reacquired(self):
        with tempfile.TemporaryDirectory() as tmp:
            old_data_dir = os.environ.get("CPA_DATA_DIR")
            os.environ["CPA_DATA_DIR"] = tmp
            try:
                first = SingleInstanceLock("test")
                second = SingleInstanceLock("test")
                self.assertTrue(first.acquire())
                self.assertFalse(second.acquire())
                first.release()
                self.assertTrue(second.acquire())
                second.release()
            finally:
                if old_data_dir is None:
                    os.environ.pop("CPA_DATA_DIR", None)
                else:
                    os.environ["CPA_DATA_DIR"] = old_data_dir

    def test_single_instance_lock_rejects_path_like_names(self):
        with self.assertRaises(ValueError):
            SingleInstanceLock("../outside")

    def test_migration_rollback_restores_configured_data_directories(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            config = root / "config"
            projects = root / "projects"
            backups = root / "backups"
            migration_backups = root / "migration_backups"
            config.mkdir()
            original = config / "app_config.json"
            original.write_text('{"default_font_size": 14}', encoding="utf-8")

            result = migrate_json_file(
                original,
                "app_config",
                backup_root=migration_backups,
                batch_id="batch-1",
            )
            self.assertTrue(result.changed)
            self.assertEqual(json.loads(original.read_text(encoding="utf-8"))["schema_version"], 1)

            restored = rollback_migration_batch(
                "batch-1",
                backup_root=migration_backups,
                config_dir=config,
                projects_dir=projects,
                backups_dir=backups,
            )

            self.assertEqual(restored, [str(original)])
            self.assertEqual(json.loads(original.read_text(encoding="utf-8")), {"default_font_size": 14})

    def test_migration_rollback_ignores_unexpected_backup_paths(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            migration_batch = root / "migration_backups" / "batch-1"
            (migration_batch / "unexpected").mkdir(parents=True)
            (migration_batch / "unexpected" / "data.json").write_text("{}", encoding="utf-8")

            restored = rollback_migration_batch(
                "batch-1",
                backup_root=root / "migration_backups",
                config_dir=root / "config",
                projects_dir=root / "projects",
                backups_dir=root / "backups",
            )

            self.assertEqual(restored, [])
            self.assertFalse((root / "unexpected" / "data.json").exists())


if __name__ == "__main__":
    unittest.main()
