"""快捷键设置面板：查看和修改全局快捷键。"""

import tkinter as tk
from tkinter import ttk

from .base import BaseSettingsPanel, bind_responsive_wrap, register_section
from ...theme import APP_BG, ROW_STRIPE, SEPARATOR, TEXT_PRIMARY, TEXT_SECONDARY, FONT_BODY, FONT_SMALL, FONT_BODY_BOLD
from ...widgets import ScrollableFrame, _make_btn
from ...shortcut_manager import shortcut_manager, DEFAULT_SHORTCUTS, ACTION_GROUPS
from ....logger import logger


@register_section
class ShortcutSettingsPanel(BaseSettingsPanel):
    section_id = "shortcuts"
    section_title = "快捷键"
    section_icon = "\u2328"  # ⌨
    section_order = 15

    # ── Build ──────────────────────────────────────────────────────────────

    def _build(self):
        sf = ScrollableFrame(self, auto_hide_ms=None, bg=APP_BG)
        sf.pack(fill=tk.BOTH, expand=True)
        inner = sf.inner

        self._accel_labels: dict[str, tk.Label] = {}

        # ── Title + subtitle ─────────────────────────────────────────────
        tk.Label(inner, text=f"{self.section_icon} 快捷键设置", font=FONT_BODY_BOLD,
                 bg=APP_BG, fg=TEXT_PRIMARY).pack(anchor="w")
        hint = tk.Label(inner, text="修改后自动保存，立即生效。",
                        font=FONT_SMALL, bg=APP_BG, fg=TEXT_SECONDARY,
                        justify="left")
        hint.pack(anchor="w", fill=tk.X, pady=(2, 8))
        bind_responsive_wrap(hint, inner, padding=4)

        # ── Action groups ────────────────────────────────────────────────
        for group_name, action_ids in ACTION_GROUPS:
            tk.Frame(inner, bg=SEPARATOR, height=1).pack(fill=tk.X, pady=12)
            tk.Label(inner, text=group_name, font=FONT_BODY_BOLD,
                     bg=APP_BG, fg=TEXT_PRIMARY).pack(anchor="w")

            for action_id in action_ids:
                if action_id not in DEFAULT_SHORTCUTS:
                    continue
                self._build_action_row(inner, action_id)

        # ── Mouse operation hints ────────────────────────────────────────
        tk.Frame(inner, bg=SEPARATOR, height=1).pack(fill=tk.X, pady=12)
        tk.Label(inner, text="鼠标操作", font=FONT_BODY_BOLD,
                 bg=APP_BG, fg=TEXT_PRIMARY).pack(anchor="w")
        mouse_hint = tk.Label(inner, text="  点击已选中行 → 取消选中",
                              font=FONT_SMALL, bg=APP_BG, fg=TEXT_SECONDARY,
                              justify="left")
        mouse_hint.pack(anchor="w", fill=tk.X, padx=8, pady=(2, 4))
        bind_responsive_wrap(mouse_hint, inner, padding=20)

        # ── Bottom: reset button ─────────────────────────────────────────
        tk.Frame(inner, bg=SEPARATOR, height=1).pack(fill=tk.X, pady=12)
        btn_frame = tk.Frame(inner, bg=APP_BG)
        btn_frame.pack(fill=tk.X, pady=(4, 8))
        _make_btn(btn_frame, "恢复默认", self._on_reset, "secondary").pack(side=tk.LEFT)

    def _build_action_row(self, parent, action_id: str):
        """Build a single shortcut row: label | accelerator | rebind button."""
        defaults = DEFAULT_SHORTCUTS[action_id]

        row = tk.Frame(parent, bg=APP_BG)
        row.pack(fill=tk.X, padx=8, pady=(4, 2))

        # Keep the action name on its own line so narrow windows do not clip it.
        action_label = tk.Label(row, text=f"  {defaults['label']}", font=FONT_BODY,
                                bg=APP_BG, fg=TEXT_SECONDARY, anchor="w",
                                justify="left")
        action_label.pack(fill=tk.X, anchor="w")
        bind_responsive_wrap(action_label, row, padding=16)

        controls = tk.Frame(row, bg=APP_BG)
        controls.pack(fill=tk.X, pady=(2, 0))

        # Accelerator display (center)
        accel_label = tk.Label(controls, text=defaults["accel"], font=FONT_BODY,
                               bg=ROW_STRIPE, fg=TEXT_PRIMARY, width=18, anchor="center",
                               relief="flat", bd=0, padx=6, pady=2)
        accel_label.pack(side=tk.LEFT, padx=(0, 8))
        self._accel_labels[action_id] = accel_label

        # Rebind button (right)
        _make_btn(controls, "重新绑定", lambda aid=action_id: self._rebind(aid),
                  "ghost").pack(side=tk.LEFT)

    # ── Rebind dialog ────────────────────────────────────────────────────

    def _rebind(self, action_id):
        """Open a small Toplevel dialog to capture a new key combination."""
        dlg = tk.Toplevel(self)
        dlg.title("设置快捷键")
        dlg.transient(self.winfo_toplevel())
        dlg.grab_set()
        dlg.configure(bg=APP_BG)
        dlg.geometry("320x120")

        title = tk.Label(dlg, text=f"为「{shortcut_manager.get_label(action_id)}」设置新快捷键",
                         font=FONT_BODY, bg=APP_BG, fg=TEXT_PRIMARY,
                         justify="left")
        title.pack(fill=tk.X, padx=16, pady=(16, 8))
        bind_responsive_wrap(title, dlg, padding=32, minimum=240)
        hint = tk.Label(dlg, text="请按下新的快捷键组合...",
                        font=FONT_SMALL, bg=APP_BG, fg=TEXT_SECONDARY)
        hint.pack()

        def on_key(event):
            # Build modifier lists
            mods = []
            accel_parts = []
            if event.state & 0x4:  # Control
                mods.append("Control")
                accel_parts.append("Ctrl")
            if event.state & 0x1:  # Shift
                mods.append("Shift")
                accel_parts.append("Shift")
            if event.state & 0x20000:  # Alt (Mod1 on some systems)
                mods.append("Alt")
                accel_parts.append("Alt")

            key = event.keysym
            if key in ("Control_L", "Control_R", "Shift_L", "Shift_R",
                        "Alt_L", "Alt_R", "Meta_L", "Meta_R"):
                return  # Modifier-only press, wait for actual key

            # Build Tk event string
            if mods:
                tk_event = "<" + "-".join(mods) + "-" + key + ">"
            else:
                tk_event = "<" + key + ">"

            # Build display accelerator
            accel_parts.append(
                key if len(key) == 1 else
                key.replace("Up", "\u2191").replace("Down", "\u2193")
                   .replace("Left", "\u2190").replace("Right", "\u2192")
                   .replace("Delete", "Del").replace("Return", "Enter")
            )
            accel_text = "+".join(accel_parts)

            # Save
            settings = shortcut_manager.get_all_settings()
            settings[action_id] = {"event": tk_event, "accel": accel_text}
            # Preserve labels for all actions
            for aid in settings:
                settings[aid]["label"] = DEFAULT_SHORTCUTS[aid]["label"]
            shortcut_manager.save_settings(settings)

            # Update UI label
            self._accel_labels[action_id].config(text=accel_text)
            dlg.destroy()

        dlg.bind("<KeyPress>", on_key)
        dlg.protocol("WM_DELETE_WINDOW", dlg.destroy)

    # ── Load / Save ──────────────────────────────────────────────────────

    def _load(self):
        """Read effective shortcuts and update all accelerator labels."""
        settings = shortcut_manager.get_all_settings()
        for action_id, data in settings.items():
            if action_id in self._accel_labels:
                self._accel_labels[action_id].config(text=data["accel"])

    def _save(self):
        # Save is handled in _rebind() directly
        pass

    def _on_reset(self):
        """Reset all shortcuts to defaults and reload UI."""
        shortcut_manager.reset_all()
        self._loading = True
        try:
            self._load()
        finally:
            self._loading = False
