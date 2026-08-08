import tkinter as tk
import threading
import unittest
from unittest.mock import patch

from src.gui.content import ContentArea
from src.project import Project


class ContentRefreshTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        try:
            cls.root = tk.Tk()
        except tk.TclError as exc:
            raise unittest.SkipTest(f"Tk display is unavailable: {exc}")
        cls.root.withdraw()

    @classmethod
    def tearDownClass(cls):
        cls.root.destroy()

    def setUp(self):
        self.content = ContentArea(self.root)
        self.content.pack(fill=tk.BOTH, expand=True)
        self.content.current_uuid = "00000000-0000-0000-0000-000000000001"
        self.content.project_data = Project.from_dict(
            {
                "project_uuid": self.content.current_uuid,
                "name": "Refresh test",
                "status": "editing",
                "created_at": "",
                "last_modified": "",
                "description": "",
                "category_order": [
                    {"id": "cat-a", "name": "A"},
                    {"id": "cat-b", "name": "B"},
                ],
                "trade_items": [
                    {
                        "id": "ti-a",
                        "category": "A",
                        "name": "One",
                        "has_unit": True,
                        "unit_price": 1,
                        "unit": "x",
                    },
                    {
                        "id": "ti-b",
                        "category": "B",
                        "name": "Two",
                        "has_unit": True,
                        "unit_price": 2,
                        "unit": "x",
                    },
                ],
                "bills": [
                    {"id": "bill-1", "trade_item_id": "ti-a", "content": "1"}
                ],
            }
        )
        self.content._render()
        self.root.update()

    def tearDown(self):
        self.content.destroy()
        self.root.update_idletasks()

    def test_bill_refresh_reuses_list_instance(self):
        view = self.content._bill_list
        parent = self.content._tab_frames["bills"]

        self.content._render_bills(parent)
        self.root.update()

        self.assertIs(view, self.content._bill_list)

    def test_worker_refresh_reuses_layout_and_category_rows(self):
        self.content.tab_var.set("workers")
        self.content._switch_tab()
        self.root.update()
        view = self.content._worker_list
        parent = self.content._tab_frames["workers"]
        category_item = self.content._category_item_widgets["A"]["item"]

        self.content._render_workers(parent)
        self.content._selected_category = "B"
        self.content._refresh_category_highlight()
        self.root.update()

        self.assertIs(view, self.content._worker_list)
        self.assertIs(category_item, self.content._category_item_widgets["A"]["item"])

    def test_project_save_queue_persists_latest_snapshot(self):
        started = threading.Event()
        release = threading.Event()
        saved = []

        def fake_update(uuid, snapshot):
            saved.append((uuid, snapshot))
            started.set()
            release.wait(2)

        try:
            with patch("src.gui.content.update_project", side_effect=fake_update):
                self.content.project_data["name"] = "first"
                self.content._save_project_async()
                self.assertTrue(started.wait(1))

                # Several edits arriving while the first disk write is in
                # progress should collapse to the newest queued snapshot.
                for name in ("middle", "latest"):
                    self.content.project_data["name"] = name
                    self.content._save_project_async()

                release.set()
                self.assertTrue(self.content.flush_project_save(2))
        finally:
            release.set()
            self.content.flush_project_save(2)

        self.assertGreaterEqual(len(saved), 2)
        self.assertEqual(saved[-1][0], self.content.current_uuid)
        self.assertEqual(saved[-1][1]["name"], "latest")

    def test_bill_tab_has_compact_add_button_for_existing_dialog(self):
        button = self.content._bill_add_button
        self.assertIsNotNone(button)
        self.assertIn("添加记录", button.cget("text"))

        with patch("src.gui.content.EditBillDialog") as dialog:
            button.invoke()

        dialog.assert_called_once()


if __name__ == "__main__":
    unittest.main()
