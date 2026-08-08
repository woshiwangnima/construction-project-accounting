import unittest
from unittest.mock import Mock

from src.gui.dialogs.settings import SettingsDialog, _clamp_settings_size
from src.gui.dialogs.settings.base import (
    BaseSettingsPanel,
    bind_responsive_wrap,
    get_sections,
    normalize_hex_color,
)


class SettingsRegistryTests(unittest.TestCase):
    class _FakeResponsiveWidget:
        def __init__(self):
            self.configured = []

        def configure(self, **kwargs):
            self.configured.append(kwargs)

    class _FakeResponsiveContainer:
        def __init__(self, width=500):
            self.width = width
            self.bound = None
            self.pending = []

        def bind(self, _sequence, callback, add=None):
            self.bound = callback
            return "binding-1"

        def winfo_width(self):
            return self.width

        def after_idle(self, callback):
            self.pending.append(callback)
            return f"idle-{len(self.pending)}"

    def test_registered_sections_are_sorted_and_unique(self):
        sections = get_sections()
        self.assertTrue(sections)
        self.assertEqual(
            [section.section_order for section in sections],
            sorted(section.section_order for section in sections),
        )
        section_ids = [section.section_id for section in sections]
        self.assertEqual(len(section_ids), len(set(section_ids)))

    def test_pending_save_is_cancelled_before_flush(self):
        panel = object.__new__(BaseSettingsPanel)
        panel._save_after_id = "after-1"
        panel._pending_save = True
        cancelled = []
        saved = []
        panel.after_cancel = lambda token: cancelled.append(token)
        panel._save = lambda: saved.append(True)

        BaseSettingsPanel.flush_pending(panel)

        self.assertEqual(cancelled, ["after-1"])
        self.assertEqual(saved, [True])
        self.assertIsNone(panel._save_after_id)
        self.assertFalse(panel._pending_save)

    def test_repeated_navigation_does_not_flush_current_panel(self):
        section = object()
        current = Mock()
        dialog = object.__new__(SettingsDialog)
        dialog._current_panel = current
        dialog._panel_cache = {section: current}
        dialog._update_nav_selection = Mock()

        SettingsDialog._show_section(dialog, section)

        current.flush_pending.assert_not_called()
        current.pack_forget.assert_not_called()
        dialog._update_nav_selection.assert_not_called()

    def test_navigation_hides_current_panel_without_synchronous_flush(self):
        current_section = object()
        next_section = object()
        current = Mock()
        next_panel = Mock()
        dialog = object.__new__(SettingsDialog)
        dialog._current_panel = current
        dialog._panel_cache = {current_section: current, next_section: next_panel}
        dialog._update_nav_selection = Mock()

        SettingsDialog._show_section(dialog, next_section)

        current.on_hide.assert_called_once_with()
        current.flush_pending.assert_not_called()
        current.pack_forget.assert_called_once_with()
        next_panel.pack.assert_called_once_with(
            fill="both", expand=True, padx=20, pady=16
        )
        self.assertIs(dialog._current_panel, next_panel)

    def test_responsive_wrap_coalesces_idle_callbacks_and_same_width_updates(self):
        widget = self._FakeResponsiveWidget()
        container = self._FakeResponsiveContainer(width=500)

        bind_responsive_wrap(widget, container, padding=20, minimum=160)
        self.assertEqual(len(container.pending), 1)

        container.bound()
        container.bound()
        self.assertEqual(len(container.pending), 1)

        container.pending.pop(0)()
        self.assertEqual(widget.configured, [{"wraplength": 480}])

        container.bound()
        self.assertEqual(len(container.pending), 0)
        self.assertEqual(widget.configured, [{"wraplength": 480}])

    def test_close_flushes_all_cached_panels_once(self):
        first = Mock()
        second = Mock()
        root = Mock()
        on_close = Mock()
        dialog = object.__new__(SettingsDialog)
        dialog._closed = False
        dialog._save_size_after_id = "resize-1"
        dialog._panel_cache = {object(): first, object(): second}
        dialog._save_size_now = Mock()
        dialog._dialog = root
        dialog._on_close_callback = on_close

        SettingsDialog._on_close(dialog, root)

        first.close.assert_called_once_with()
        second.close.assert_called_once_with()
        root.after_cancel.assert_called_once_with("resize-1")
        dialog._save_size_now.assert_called_once_with()
        root.destroy.assert_called_once_with()
        on_close.assert_called_once_with()
        self.assertTrue(dialog._closed)

    def test_size_and_color_values_are_normalized(self):
        self.assertEqual(_clamp_settings_size([1, 2]), (700, 500))
        self.assertIsNone(_clamp_settings_size(["bad", 500]))
        self.assertEqual(normalize_hex_color(" #AAbbCC ", "#000000"), "#aabbcc")
        self.assertEqual(normalize_hex_color("not-a-color", "#000000"), "#000000")


if __name__ == "__main__":
    unittest.main()
