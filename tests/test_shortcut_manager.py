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

    def test_tk_event_translates_to_qkey_sequence(self):
        cases = {
            "new_project": "Ctrl+N",
            "add_record": "Ctrl+Return",
            "save_image": "Ctrl+Shift+S",
            "toggle_display": "Alt+D",
            "rollback": "F4",
            "edit_project": "Alt+E",
            "open_location": "Alt+F",
            "delete_project": "Alt+Delete",
            "delete_category": "Alt+Shift+Delete",
            "move_up": "Alt+Up",
            "move_down": "Alt+Down",
            "edit_trade": "F2",
            "delete_item": "Delete",
            "copy": "Ctrl+C",
            "paste": "Ctrl+V",
            "pin_project": "Ctrl+Shift+P",
        }
        for action_id, expected in cases.items():
            self.assertEqual(
                self.manager.get_qkey(action_id), expected, action_id
            )

    def test_qkey_falls_back_to_default_when_user_config_breaks(self):
        with patch.object(self.manager, "_load_user_shortcuts", return_value={"new_project": {"event": "garbage"}}):
            self.assertEqual(self.manager.get_qkey("new_project"), "")

    def test_qkey_empty_for_unknown_action(self):
        self.assertEqual(self.manager.get_qkey("does_not_exist"), "")


if __name__ == "__main__":
    unittest.main()
