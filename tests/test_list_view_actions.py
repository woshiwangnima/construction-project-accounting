import tkinter as tk
import unittest

from src.gui.widgets.list_view_base import ListViewBase


class DemoListView(ListViewBase):
    """Small concrete list used to exercise the shared action toolbar."""

    def _create_row_widgets(self, row_frame, idx, item):
        return {}


class VariableHeightListView(DemoListView):
    """List fixture that mirrors wrapped rows without creating many cells."""

    def _create_row_widgets(self, row_frame, idx, item):
        content = tk.Frame(
            row_frame,
            width=120,
            height=int(item.get("height", 48)),
            bg="white",
        )
        content.grid(row=0, column=0, sticky="nsew")
        row_frame.grid_columnconfigure(0, weight=1)
        content.pack_propagate(False)
        return {"name": content}


class ListViewActionTests(unittest.TestCase):
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

    def make_view(self, items=None, editable=True, callbacks=True):
        events = []
        callback = (lambda name: lambda idx: events.append((name, idx))) if callbacks else None
        view = DemoListView(
            self.root,
            columns=("name", "actions"),
            action_col="actions",
            default_weights={"name": 0.9, "actions": 0.1},
            initial_items=list(items or []),
            shared_actions=True,
            editable=editable,
            on_row_activated=callback("edit") if callback else None,
            on_copy=callback("copy") if callback else None,
            on_paste=callback("paste") if callback else None,
            on_move_up=callback("move_up") if callback else None,
            on_move_down=callback("move_down") if callback else None,
            on_delete=callback("delete") if callback else None,
            paste_enabled=True,
            paste_allowed=True,
        )
        self.root.update_idletasks()
        return view, events

    @staticmethod
    def menu_state(view, action):
        index = view._action_menu_indices[action]
        return view._action_menu.entrycget(index, "state")

    def tearDown(self):
        for child in self.root.winfo_children():
            child.destroy()
        self.root.update_idletasks()

    def test_action_trigger_stays_clickable_without_selection(self):
        view, _ = self.make_view(callbacks=False)
        self.assertEqual(view._action_button.cget("state"), tk.NORMAL)

        view._action_button.event_generate("<ButtonPress-1>")
        self.root.update()
        # The test root is withdrawn, so Tk does not map the popup.  The
        # important regression is that the press is accepted by a normal
        # Menubutton instead of being rejected at the trigger level.
        self.assertEqual(view._action_button.cget("state"), tk.NORMAL)

    def test_menu_state_tracks_selected_row(self):
        view, _ = self.make_view(items=[{}, {}])
        view.set_selected_index(0)

        self.assertEqual(self.menu_state(view, "edit"), tk.NORMAL)
        self.assertEqual(self.menu_state(view, "copy"), tk.NORMAL)
        self.assertEqual(self.menu_state(view, "paste"), tk.NORMAL)
        self.assertEqual(self.menu_state(view, "move_up"), tk.DISABLED)
        self.assertEqual(self.menu_state(view, "move_down"), tk.NORMAL)
        self.assertEqual(self.menu_state(view, "delete"), tk.NORMAL)

    def test_menu_invoke_calls_callback_for_selected_row(self):
        view, events = self.make_view(items=[{}, {}])
        view.set_selected_index(1)
        view._action_menu.invoke(view._action_menu_indices["edit"])
        view._action_menu.invoke(view._action_menu_indices["copy"])

        self.assertEqual(events, [("edit", 1), ("copy", 1)])

    def test_read_only_menu_keeps_copy_available(self):
        view, _ = self.make_view(items=[{}], editable=False)
        view.set_selected_index(0)

        self.assertEqual(view._action_button.cget("state"), tk.NORMAL)
        self.assertEqual(self.menu_state(view, "copy"), tk.NORMAL)
        for action in ("edit", "paste", "move_up", "move_down", "delete"):
            self.assertEqual(self.menu_state(view, action), tk.DISABLED)

    def test_large_list_only_materializes_visible_rows(self):
        view, events = self.make_view(items=[{} for _ in range(300)])
        self.root.update()

        self.assertTrue(view._virtualized)
        self.assertLess(len(view._row_frames), len(view._items))

        view.set_selected_index(299)
        self.root.update()
        self.assertEqual(view.get_selected_index(), 299)
        self.assertIn(299, view._row_indices)
        view._action_menu.invoke(view._action_menu_indices["edit"])
        self.assertEqual(events[-1], ("edit", 299))

    def test_variable_height_scroll_keeps_target_row_and_anchor(self):
        self.root.geometry("1000x700")
        items = [{"height": 48} for _ in range(120)]
        items[1]["height"] = 160
        items[2]["height"] = 240
        items[70]["height"] = 180
        view = VariableHeightListView(
            self.root,
            columns=("name", "actions"),
            action_col="actions",
            default_weights={"name": 0.9, "actions": 0.1},
            initial_items=items,
            shared_actions=True,
            editable=True,
        )
        view.pack(fill=tk.BOTH, expand=True)
        self.root.update_idletasks()
        self.root.update()

        view.scroll_to_index(70)
        self.root.update_idletasks()
        self.root.update()

        self.assertTrue(view._virtualized)
        self.assertIn(70, view._row_indices)
        self.assertEqual(view.get_top_scroll_anchor()["index"], 70)
        row = view._get_row_frame(70)
        self.assertIsNotNone(row)
        self.assertEqual(view._row_index_at_y_root(row.winfo_rooty() + 1), 70)


if __name__ == "__main__":
    unittest.main()
