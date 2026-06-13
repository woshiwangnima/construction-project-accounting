"""关于面板。"""

import tkinter as tk
import webbrowser

from .base import BaseSettingsPanel, register_section
from ...theme import APP_BG, TEXT_PRIMARY, FONT_BODY, FONT_SMALL, FONT_BODY_BOLD
from ...widgets import ScrollableFrame, _make_btn
from ....config_loader import load_app
from ....versioning import APP_VERSION


@register_section
class AboutSettingsPanel(BaseSettingsPanel):
    section_id = "about"
    section_title = "关于"
    section_icon = "ℹ"
    section_order = 99

    def _build(self):
        sf = ScrollableFrame(self, auto_hide_ms=None, bg=APP_BG)
        sf.pack(fill=tk.BOTH, expand=True)
        inner = sf.inner

        tk.Label(inner, text=f"{self.section_icon} 关于", font=FONT_BODY_BOLD,
                 bg=APP_BG, fg=TEXT_PRIMARY).pack(anchor="w")
        self._version_var = tk.StringVar()
        tk.Label(inner, textvariable=self._version_var, font=FONT_BODY,
                 bg=APP_BG, fg=TEXT_PRIMARY).pack(anchor="w", pady=(8, 16))

        REPO_URL = "https://github.com/woshiwangnima/construction-project-accounting"
        github_link = tk.Label(
            inner, text=f"GitHub: {REPO_URL}",
            font=FONT_SMALL, bg=APP_BG, fg="#2b6cb0", cursor="hand2",
        )
        github_link.pack(anchor="w", pady=(4, 8))
        github_link.bind("<Button-1>", lambda e: webbrowser.open(REPO_URL))

        _make_btn(inner, "\u21bb 检查更新", self._check_update, "secondary").pack(anchor="w", pady=(4, 8))

        tk.Label(inner, text="版本更新说明", font=FONT_BODY_BOLD,
                 bg=APP_BG, fg=TEXT_PRIMARY).pack(anchor="w")
        notes_frame = tk.Frame(inner, bg=APP_BG)
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

    def _check_update(self):
        try:
            from ....updater import check_for_update, UpdateChecker
            from ..update_dialog import UpdateDialog
            checker = UpdateChecker()
            info = check_for_update()
            if info is None:
                from tkinter import messagebox
                messagebox.showinfo("检查更新", "当前已是最新版本。", parent=self)
            else:
                UpdateDialog(self.winfo_toplevel(), info)
        except Exception as e:
            from tkinter import messagebox
            messagebox.showerror("检查更新失败", str(e))

    def _save(self):
        return
