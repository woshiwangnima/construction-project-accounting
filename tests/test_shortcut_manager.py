import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

from src.gui.shortcut_manager import ShortcutManager


class ShortcutManagerTests(unittest.TestCase):
    def setUp(self):
        self.sidebar = SimpleNamespace(
            selected_uuid="project-1",
            _open_rollback_dialog=Mock(),
            _edit_project=Mock(),
            _open_file_location=Mock(),
            _delete_project=Mock(),
        )
        self.content = SimpleNamespace(
            tab_var=SimpleNamespace(get=lambda: "bills"),
            current_uuid="project-1",
        )
        self.manager = ShortcutManager()
        self.manager._main = SimpleNamespace(
            sidebar=self.sidebar,
            content=self.content,
        )

    def test_project_shortcuts_use_public_selected_uuid(self):
        self.manager._execute_action("rollback")
        self.manager._execute_action("edit_project")
        self.manager._execute_action("open_location")

        self.sidebar._open_rollback_dialog.assert_called_once_with("project-1")
        self.sidebar._edit_project.assert_called_once_with("project-1")
        self.sidebar._open_file_location.assert_called_once_with("project-1")

    def test_delete_shortcut_uses_project_manager_get_project(self):
        project = {"project_uuid": "project-1", "status": "editing"}
        with patch("src.project_manager.get_project", return_value=project) as get_project:
            self.manager._execute_action("delete_project")

        get_project.assert_called_once_with("project-1")
        self.sidebar._delete_project.assert_called_once_with("project-1", project)


if __name__ == "__main__":
    unittest.main()
