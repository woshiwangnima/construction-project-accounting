import unittest
from unittest.mock import Mock, patch

from src.gui.sidebar import Sidebar


class SidebarDeleteTests(unittest.TestCase):
    @staticmethod
    def make_sidebar(flush_result=True):
        sidebar = object.__new__(Sidebar)
        sidebar.selected_uuid = "project-1"
        sidebar.on_select = Mock()
        sidebar.refresh = Mock()
        sidebar.winfo_toplevel = Mock(return_value=None)
        sidebar._project_for_context_menu = Mock(
            return_value={"project_uuid": "project-1", "name": "项目", "status": "editing"}
        )
        sidebar._confirm_delete = Mock(return_value=True)
        sidebar._flush_saves = Mock(return_value=flush_result)
        return sidebar

    def test_delete_waits_for_project_save_queue(self):
        sidebar = self.make_sidebar()
        events = []
        sidebar._flush_saves.side_effect = lambda: events.append("flush") or True

        with patch("src.gui.sidebar.delete_project", side_effect=lambda uuid: events.append("delete") or True):
            Sidebar._delete_project(sidebar, "project-1", {"status": "editing"})

        self.assertEqual(events, ["flush", "delete"])

    def test_delete_stops_when_save_queue_did_not_finish(self):
        sidebar = self.make_sidebar(flush_result=False)
        with patch("src.gui.sidebar.delete_project") as delete_project, \
                patch("src.gui.sidebar.messagebox.showwarning") as warning:
            Sidebar._delete_project(sidebar, "project-1", {"status": "editing"})

        delete_project.assert_not_called()
        warning.assert_called_once()


if __name__ == "__main__":
    unittest.main()
