"""关于面板。"""

import tkinter as tk

from .base import BaseSettingsPanel, register_section
from ...theme import APP_BG, TEXT_PRIMARY, TEXT_SECONDARY, FONT_BODY, FONT_SMALL, FONT_BODY_BOLD
from ....config_loader import load_app
from ....versioning import APP_VERSION


@register_section
class AboutSettingsPanel(BaseSettingsPanel):
    section_id = "about"
    section_title = "关于"
    section_icon = "ℹ"
    section_order = 99

    def _build(self):
        tk.Label(self, text=f"{self.section_icon} 关于", font=FONT_BODY_BOLD, bg=APP_BG, fg=TEXT_PRIMARY).pack(anchor="w")
        self._version_var = tk.StringVar()
        tk.Label(self, textvariable=self._version_var, font=FONT_BODY,
                 bg=APP_BG, fg=TEXT_PRIMARY).pack(anchor="w", pady=(8, 16))
        tk.Label(self, text="版本更新说明", font=FONT_BODY_BOLD,
                 bg=APP_BG, fg=TEXT_PRIMARY).pack(anchor="w")
        notes_frame = tk.Frame(self, bg=APP_BG)
        notes_frame.pack(fill=tk.BOTH, expand=True, pady=(8, 0))
        self._notes_scrollbar = tk.Scrollbar(notes_frame, orient=tk.VERTICAL)
        self._notes = tk.Text(notes_frame, height=20, font=FONT_SMALL, wrap="word",
                              bg="white", fg=TEXT_PRIMARY, relief="solid", bd=1,
                              yscrollcommand=self._notes_scrollbar.set)
        self._notes_scrollbar.config(command=self._notes.yview)
        self._notes.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        self._notes_scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self._notes.config(state=tk.DISABLED)

    def _load(self):
        cfg = load_app()
        self._version_var.set(f"当前版本：{cfg.get('app_version', APP_VERSION)}")
        lines = []
        for item in cfg.get("release_notes", []) or []:
            version = item.get("version", "")
            date = item.get("date", "")
            lines.append(f"v{version}  {date}".strip())
            for note in item.get("notes", []) or []:
                lines.append(f"- {note}")
            lines.append("")
        self._notes.config(state=tk.NORMAL)
        self._notes.delete("1.0", tk.END)
        self._notes.insert("1.0", "\n".join(lines).strip())
        self._notes.config(state=tk.DISABLED)

    def _save(self):
        return
