import tkinter as tk
import unittest
from unittest.mock import Mock

from src.gui.main_window import MainInterface


class MainWindowCloseTests(unittest.TestCase):
    def test_close_always_destroys_root_when_cleanup_fails(self):
        try:
            root = tk.Tk()
        except tk.TclError as exc:
            self.skipTest(f"Tk display is unavailable: {exc}")
        root.withdraw()
        try:
            app = MainInterface(root)
            self.assertIs(app.sidebar._flush_saves.__self__, app.content)
            app.content.flush_project_save = Mock(side_effect=OSError("save failed"))
            app._save_window_geometry = Mock(side_effect=OSError("config failed"))

            app._on_close()

            with self.assertRaises(tk.TclError):
                root.winfo_exists()
        finally:
            try:
                if root.winfo_exists():
                    root.destroy()
            except tk.TclError:
                pass


if __name__ == "__main__":
    unittest.main()
