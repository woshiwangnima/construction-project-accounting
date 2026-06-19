"""新建项目对话框"""

import tkinter as tk
from tkinter import messagebox
from datetime import datetime

from ..theme import APP_BG
from ..font_manager import font_manager
from ..widgets import _make_btn, _input_entry, DateTypeSelector
from ...project_manager import create_project, update_project
from ...config_loader import load_app, load_user


DEFAULT_NEW_PROJECT_SIZE = (640, 420)
_MIN_NEW_PROJECT_SIZE = (640, 380)

_DESC_PLACEHOLDER = "输入项目简介，默认为空"


def _resolve_new_project_size() -> tuple[int, int]:
    for cfg in (load_user(), load_app()):
        size = (cfg.get("window_sizes") or {}).get("new_project")
        if isinstance(size, list) and len(size) == 2:
            w = max(int(size[0]), _MIN_NEW_PROJECT_SIZE[0])
            h = max(int(size[1]), _MIN_NEW_PROJECT_SIZE[1])
            return w, h
    return DEFAULT_NEW_PROJECT_SIZE


class NewProjectDialog:
    def __init__(self, parent, on_done=None, mode="new", project_data=None):
        self.on_done = on_done
        self.mode = mode
        self.project_data = project_data or {}
        dialog = tk.Toplevel(parent)
        dialog.title("编辑项目" if mode == "edit" else "新建项目")
        dialog.resizable(False, False)
        dialog.transient(parent)
        dialog.grab_set()
        dialog.configure(bg=APP_BG)

        w, h = _resolve_new_project_size()
        x = parent.winfo_rootx() + (parent.winfo_width() - w) // 2
        y = parent.winfo_rooty() + (parent.winfo_height() - h) // 2
        dialog.geometry(f"{w}x{h}+{x}+{y}")

        tk.Label(dialog, text="\U0001f4dd 项目名称", font=font_manager.get("body"), bg=APP_BG).pack(pady=(20, 4), padx=20, anchor="w")
        initial_name = self.project_data.get("name", "")
        self.name_entry, self.name_var = _input_entry(dialog, placeholder="如：XX小区装修", value=initial_name)
        self.name_entry.pack(fill=tk.X, padx=20)
        self.name_entry.focus_set()

        tk.Label(dialog, text="\U0001f4c5 项目日期", font=font_manager.get("body"), bg=APP_BG).pack(pady=(14, 4), padx=20, anchor="w")
        date_frame = tk.Frame(dialog, bg=APP_BG)
        date_frame.pack(fill=tk.X, padx=20)
        self.date_selector = DateTypeSelector(
            date_frame,
            default_type="单个时间",
            default_start=datetime.now().strftime("%Y-%m-%d"),
        )
        self.date_selector.pack(fill=tk.X)
        if mode == "edit":
            self.date_selector.set(
                self.project_data.get("project_date_type", "无时间"),
                self.project_data.get("project_date_start", ""),
                self.project_data.get("project_date_end", ""),
            )

        tk.Label(dialog, text="\U0001f4dd 项目描述", font=font_manager.get("body"), bg=APP_BG).pack(pady=(14, 4), padx=20, anchor="w")
        desc_frame = tk.Frame(dialog, bg=APP_BG)
        desc_frame.pack(fill=tk.X, padx=20)
        self.desc_text = tk.Text(desc_frame, height=3, wrap="word", font=font_manager.get("body"), relief="solid", borderwidth=1)
        self.desc_text.pack(fill=tk.X)

        initial_desc = self.project_data.get("description", "")
        if initial_desc:
            self.desc_text.insert("1.0", initial_desc)
            self.desc_text.config(foreground="black")
        else:
            self.desc_text.insert("1.0", _DESC_PLACEHOLDER)
            self.desc_text.config(foreground="gray")

        def _on_desc_focus_in(e):
            if self.desc_text.get("1.0", "end-1c") == _DESC_PLACEHOLDER:
                self.desc_text.delete("1.0", tk.END)
                self.desc_text.config(foreground="black")

        def _on_desc_focus_out(e):
            if not self.desc_text.get("1.0", "end-1c").strip():
                self.desc_text.delete("1.0", tk.END)
                self.desc_text.insert("1.0", _DESC_PLACEHOLDER)
                self.desc_text.config(foreground="gray")

        self.desc_text.bind("<FocusIn>", _on_desc_focus_in)
        self.desc_text.bind("<FocusOut>", _on_desc_focus_out)

        btn_frame = tk.Frame(dialog, bg=APP_BG)
        btn_frame.pack(pady=(20, 0))
        _make_btn(btn_frame, "取消", dialog.destroy, "ghost").pack(side=tk.LEFT, padx=4)
        btn_text = "保存" if mode == "edit" else "创建"
        _make_btn(btn_frame, btn_text, lambda: self._confirm(dialog), "primary").pack(side=tk.LEFT, padx=4)

    def _confirm(self, dialog):
        name = self.name_var.get().strip()
        if not name:
            messagebox.showwarning("提示", "请输入项目名称", parent=dialog)
            return

        desc = self.desc_text.get("1.0", "end-1c").strip()
        if desc == _DESC_PLACEHOLDER:
            desc = ""

        date_type, date_start, date_end = self.date_selector.get()

        if self.mode == "edit":
            pd = self.project_data
            pd["name"] = name
            pd["description"] = desc
            pd["project_date_type"] = date_type
            pd["project_date_start"] = date_start
            pd["project_date_end"] = date_end
            uuid = pd.get("project_uuid", "")
            update_project(uuid, pd)
        else:
            create_project(
                name,
                description=desc,
                project_date_type=date_type,
                project_date_start=date_start,
                project_date_end=date_end,
            )
        dialog.destroy()
        if self.on_done:
            self.on_done()
