import json
import os
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch

from src import project_manager as pm
from src import project_repository as repository
from src.project import Project


class ProjectRepositoryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.projects = self.root / "projects"
        self.backups = self.root / "backups"
        self.projects.mkdir()
        self.backups.mkdir()
        self.environment = patch.dict(os.environ, {
            "CPA_PROJECTS_DIR": str(self.projects),
            "CPA_BACKUPS_DIR": str(self.backups),
            "CPA_CONFIG_DIR": str(self.root / "config"),
        })
        self.environment.start()
        pm._invalidate_list_cache()
        self.uuid = "11111111-1111-1111-1111-111111111111"
        self.path = self.projects / f"p_{self.uuid}.json"

    def tearDown(self):
        pm._invalidate_list_cache()
        self.environment.stop()
        self.temp.cleanup()

    def write_project(self, name="original", **overrides):
        project = Project.from_dict({
            "project_uuid": self.uuid,
            "name": name,
            "view_state": {"lists": {"bills": {"item_id": "original"}}},
            **overrides,
        })
        self.path.write_text(json.dumps(project.to_dict()), encoding="utf-8")
        return project

    def test_listing_returns_isolated_projects_and_nested_state(self):
        self.write_project()
        first = pm.list_projects()
        first[0].name = "unsaved"
        first[0].view_state["lists"]["bills"]["item_id"] = "unsaved"
        first.clear()

        second = pm.list_projects()
        self.assertEqual(len(second), 1)
        self.assertEqual(second[0].name, "original")
        self.assertEqual(second[0].view_state["lists"]["bills"]["item_id"], "original")
        second[0].name = "another unsaved edit"
        self.assertEqual(pm.list_projects()[0].name, "original")

    def test_listing_cache_includes_configured_directory(self):
        first = self.write_project(name="first")
        fixed_time = 1_700_000_000_000_000_000
        os.utime(self.path, ns=(fixed_time, fixed_time))
        os.utime(self.projects, ns=(fixed_time, fixed_time))
        self.assertEqual(pm.list_projects()[0].name, "first")

        other = self.root / "other"
        other.mkdir()
        first.name = "other"
        other_path = other / self.path.name
        other_path.write_text(json.dumps(first.to_dict()), encoding="utf-8")
        os.utime(other_path, ns=(fixed_time, fixed_time))
        os.utime(other, ns=(fixed_time, fixed_time))
        with patch.dict(os.environ, {"CPA_PROJECTS_DIR": str(other)}):
            self.assertEqual(pm.list_projects()[0].name, "other")

    def test_listing_detects_in_place_file_changes(self):
        self.write_project()
        self.assertEqual(pm.list_projects()[0].name, "original")
        directory_stat = self.projects.stat()
        file_stat = self.path.stat()

        self.write_project(name="modified")
        os.utime(self.path, ns=(file_stat.st_atime_ns, file_stat.st_mtime_ns + 1_000_000))
        os.utime(self.projects, ns=(directory_stat.st_atime_ns, directory_stat.st_mtime_ns))
        self.assertEqual(pm.list_projects()[0].name, "modified")

    def test_recovery_skips_invalid_latest_backup_and_keeps_pin(self):
        project = self.write_project()
        valid_backup = self.backups / f"p_{self.uuid}.1.json"
        valid_backup.write_text(json.dumps(project.to_dict()), encoding="utf-8")
        invalid_backup = self.backups / f"p_{self.uuid}.2.json"
        invalid_backup.write_text("[]", encoding="utf-8")
        os.utime(valid_backup, (1, 1))
        os.utime(invalid_backup, (2, 2))
        self.path.write_text('{"is_pinned": true, "bills": 1}', encoding="utf-8")

        recovered = pm.get_project(self.uuid)
        self.assertIsNotNone(recovered)
        self.assertEqual(recovered.name, "original")
        self.assertTrue(recovered.is_pinned)
        stored = json.loads(self.path.read_text(encoding="utf-8"))
        self.assertEqual(stored["name"], "original")
        self.assertTrue(stored["is_pinned"])

    def test_update_preserves_disk_pin_and_facade_backup_settings(self):
        project = self.write_project()
        self.assertTrue(pm.toggle_pin(self.uuid))
        with patch("src.project_manager._get_backup_count", return_value=1):
            for value in ("first change", "second change"):
                project.name = value
                pm.update_project(self.uuid, project)

        stored = pm.get_project(self.uuid)
        self.assertEqual(stored.name, "second change")
        self.assertTrue(stored.is_pinned)
        backups = list(self.backups.glob(f"p_{self.uuid}.*.json"))
        self.assertEqual(len(backups), 1)
        self.assertEqual(json.loads(backups[0].read_text(encoding="utf-8"))["name"], "first change")

    def test_recovery_keeps_a_save_completed_while_waiting_for_write_lock(self):
        project = self.write_project()
        backup = self.backups / f"p_{self.uuid}.1.json"
        backup.write_text(json.dumps(project.to_dict()), encoding="utf-8")
        self.path.write_text("broken", encoding="utf-8")
        lock = pm._project_write_lock(self.uuid)
        lock_requested = threading.Event()
        recovered = []

        def recovery_lock(project_uuid):
            lock_requested.set()
            return lock

        lock.acquire()
        thread = threading.Thread(target=lambda: recovered.append(pm.get_project(self.uuid)), daemon=True)
        with patch.object(repository, "_project_write_lock", side_effect=recovery_lock):
            try:
                thread.start()
                self.assertTrue(lock_requested.wait(timeout=2), "Recovery never reached its write lock")
                self.write_project(name="saved while recovery waited", is_pinned=True)
            finally:
                lock.release()
            thread.join(timeout=2)

        self.assertFalse(thread.is_alive(), "Recovery deadlocked")
        self.assertEqual(recovered[0].name, "saved while recovery waited")
        self.assertTrue(recovered[0].is_pinned)
        self.assertEqual(pm.get_project(self.uuid).name, "saved while recovery waited")


if __name__ == "__main__":
    unittest.main()
