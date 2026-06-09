"""新建项目对话框"""

import tkinter as tk
from tkinter import messagebox
from datetime import datetime

from ..theme import APP_BG, FONT_BODY
from ..widgets import _make_btn, _input_entry, DateTypeSelector
from ...project_manager import create_project
from ...config_loader import load_app, load_user


DEFAULT_NEW_PROJECT_SIZE = (640, 420)
_MIN_NEW_PROJECT_SIZE = (640, 380)


def _resolve_new_project_size() -> tuple[int, int]:
    for cfg in (load_user(), load_app()):
        size = (cfg.get("window_sizes") or {}).get("new_project")
        if isinstance(size, list) and len(size) == 2:
            w = max(int(size[0]), _MIN_NEW_PROJECT_SIZE[0])
            h = max(int(size[1]), _MIN_NEW_PROJECT_SIZE[1])
            return w, h
    return DEFAULT_NEW_PROJECT_SIZE


class NewProjectDialog:
    def __init__(self, parent, on_done=None):
        self.on_done = on_done
        dialog = tk.Toplevel(parent)
        dialog.title("新建项目")
        dialog.resizable(False, False)
        dialog.transient(parent)
        dialog.grab_set()
        dialog.configure(bg=APP_BG)

        w, h = _resolve_new_project_size()
        x = parent.winfo_rootx() + (parent.winfo_width() - w) // 2
        y = parent.winfo_rooty() + (parent.winfo_height() - h) // 2
        dialog.geometry(f"{w}x{h}+{x}+{y}")

        tk.Label(dialog, text="\U0001f4dd 项目名称", font=FONT_BODY, bg=APP_BG).pack(pady=(20, 4), padx=20, anchor="w")
        self.name_entry, self.name_var = _input_entry(dialog, placeholder="如：XX小区装修")
        self.name_entry.pack(fill=tk.X, padx=20)
        self.name_entry.focus_set()

        tk.Label(dialog, text="\U0001f4c5 项目日期", font=FONT_BODY, bg=APP_BG).pack(pady=(14, 4), padx=20, anchor="w")
        date_frame = tk.Frame(dialog, bg=APP_BG)
        date_frame.pack(fill=tk.X, padx=20)
        self.date_selector = DateTypeSelector(
            date_frame,
            default_type="单个时间",
            default_start=datetime.now().strftime("%Y-%m-%d"),
        )
        self.date_selector.pack(fill=tk.X)

        btn_frame = tk.Frame(dialog, bg=APP_BG)
        btn_frame.pack(pady=(20, 0))
        _make_btn(btn_frame, "取消", dialog.destroy, "ghost").pack(side=tk.LEFT, padx=4)
        _make_btn(btn_frame, "创建", lambda: self._confirm(dialog), "primary").pack(side=tk.LEFT, padx=4)

    def _confirm(self, dialog):
        name = self.name_var.get().strip()
        if not name:
            messagebox.showwarning("提示", "请输入项目名称", parent=dialog)
            return

        date_type, date_start, date_end = self.date_selector.get()
        create_project(
            name,
            project_date_type=date_type,
            project_date_start=date_start,
            project_date_end=date_end,
        )
        dialog.destroy()
        if self.on_done:
            self.on_done()
