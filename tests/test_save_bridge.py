"""Deterministic slow-disk and failed-save regression tests."""
import threading
import unittest
from unittest.mock import patch

from src.gui.qt.save_bridge import ProjectSaveBridge


class SaveBridgeTests(unittest.TestCase):
    def test_slow_save_keeps_each_project_and_latest_snapshot(self):
        entered = threading.Event()
        release = threading.Event()
        writes = []

        def save(uuid, snapshot):
            if not writes:
                entered.set()
                if not release.wait(5):
                    raise TimeoutError("test worker was not released")
            writes.append((uuid, snapshot["value"]))

        bridge = ProjectSaveBridge()
        with patch("src.gui.qt.save_bridge.update_project", side_effect=save):
            try:
                bridge.schedule("a", {"value": 1})
                self.assertTrue(entered.wait(5))
                bridge.schedule("a", {"value": 2})
                bridge.schedule("b", {"value": 3})
                snapshot = {"value": 4}
                bridge.schedule("a", snapshot)
                snapshot["value"] = 99
                self.assertFalse(bridge.close(0))
                bridge.schedule("c", {"value": 5})
            finally:
                release.set()
                closed = bridge.close(5)
            self.assertTrue(closed)
        self.assertEqual(writes, [("a", 1), ("a", 4), ("b", 3), ("c", 5)])

    def test_failed_snapshot_survives_close_and_can_retry(self):
        bridge = ProjectSaveBridge()
        with patch("src.gui.qt.save_bridge.update_project", side_effect=OSError("disk full")):
            bridge.schedule("a", {"value": 1})
            self.assertTrue(bridge._idle.wait(5))
            self.assertFalse(bridge.close(5))
        with patch("src.gui.qt.save_bridge.update_project") as save:
            self.assertTrue(bridge.close(5))
            save.assert_called_once_with("a", {"value": 1})

    def test_new_edit_supersedes_failed_snapshot(self):
        bridge = ProjectSaveBridge()
        with patch("src.gui.qt.save_bridge.update_project", side_effect=OSError("disk full")):
            bridge.schedule("a", {"value": 1})
            self.assertTrue(bridge._idle.wait(5))
        with patch("src.gui.qt.save_bridge.update_project") as save:
            bridge.schedule("a", {"value": 2})
            self.assertTrue(bridge.close(5))
            save.assert_called_once_with("a", {"value": 2})

    def test_other_project_success_does_not_hide_failed_save(self):
        bridge = ProjectSaveBridge()

        def save(uuid, snapshot):
            if uuid == "a":
                raise OSError("disk full")

        with patch("src.gui.qt.save_bridge.update_project", side_effect=save):
            bridge.schedule("a", {"value": 1})
            self.assertTrue(bridge._idle.wait(5))
            bridge.schedule("b", {"value": 2})
            self.assertTrue(bridge._idle.wait(5))
            self.assertFalse(bridge.flush(5))
        with patch("src.gui.qt.save_bridge.update_project") as retry:
            self.assertTrue(bridge.close(5))
            retry.assert_called_once_with("a", {"value": 1})
