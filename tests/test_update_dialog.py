import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

from src.gui.dialogs.update_dialog import UpdateDialog


class UpdateDialogTests(unittest.TestCase):
    @staticmethod
    def make_dialog(callback):
        dialog = object.__new__(UpdateDialog)
        dialog._status_var = Mock()
        dialog._download_btn = Mock()
        dialog.update_idletasks = Mock()
        dialog.grab_release = Mock()
        dialog.destroy = Mock()
        dialog._on_close_callback = callback
        return dialog

    def test_download_apply_calls_close_callback(self):
        callback = Mock()
        dialog = self.make_dialog(callback)
        with patch("src.gui.dialogs.update_dialog.confirm_dialog", return_value=True), \
                patch("src.gui.dialogs.update_dialog.apply_update") as apply_update:
            dialog._on_download_complete("update-dir")

        apply_update.assert_called_once_with("update-dir")
        callback.assert_called_once_with()
        dialog.destroy.assert_not_called()

    def test_download_apply_without_callback_destroys_dialog(self):
        dialog = self.make_dialog(None)
        with patch("src.gui.dialogs.update_dialog.confirm_dialog", return_value=True), \
                patch("src.gui.dialogs.update_dialog.apply_update"):
            dialog._on_download_complete("update-dir")

        dialog.destroy.assert_called_once_with()

    def test_find_close_callback_walks_to_root(self):
        callback = Mock()
        root = SimpleNamespace(_app_close_callback=callback, master=None)
        child = SimpleNamespace(master=root)

        self.assertIs(UpdateDialog._find_close_callback(child), callback)


if __name__ == "__main__":
    unittest.main()
