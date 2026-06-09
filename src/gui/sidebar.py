"""左侧项目列表侧边栏"""

import os
import subprocess
import sys
import tkinter as tk
from tkinter import ttk, messagebox, filedialog
from typing import Optional

from .theme import (
    SIDEBAR_BG, SIDEBAR_FG, SIDEBAR_HOVER,
    SIDEBAR_HEADER_BG, SIDEBAR_HEADER_FG,
    SIDEBAR_SELECTED_BG, SIDEBAR_SELECTED_FG,
    SIDEBAR_ITEM_BORDER, ACCENT,
    TEXT_SECONDARY, TEXT_PRIMARY,
    FONT_BODY, FONT_BODY_BOLD, FONT_SMALL, FONT_HEADING,
)
from .widgets import _make_btn, _input_entry
from .widgets.canvas_scroll import scroll_canvas_units_clamped
from .dialogs.new_project import NewProjectDialog
from ..project_manager import list_projects, delete_project, export_project, import_project, project_file_path, PROJECTS_DIR
from ..project_status import ProjectStatus
from .editability import EditabilityPolicy


class Sidebar(ttk.Frame):
    ROLLBACK_MENU_LABEL = "\U0001f504\ufe0f 回滚存档"

    def __init__(self, parent, on_select, editability=None, on_settings_closed=None):
        super().__init__(parent, width=320)
        self.pack_propagate(False)
        self.on_select = on_select
        self.selected_uuid = None
        self._editability: Optional[EditabilityPolicy] = editability
        self._on_settings_closed = on_settings_closed
        self._build_ui()
        self.refresh()

    def _build_ui(self):
        header = tk.Frame(self, bg=SIDEBAR_HEADER_BG, height=70)
        header.pack(fill=tk.X)
        header.pack_propagate(False)
        tk.Label(header, text="\U0001f3d7\ufe0f 施工项目记账", font=FONT_HEADING,
                 bg=SIDEBAR_HEADER_BG, fg=SIDEBAR_HEADER_FG).pack(expand=True)

        ctrl = tk.Frame(self, bg=SIDEBAR_BG, pady=10, padx=10)
        ctrl.pack(fill=tk.X)
        _make_btn(ctrl, "\u2795 新建项目", self._new_project, "primary").pack(fill=tk.X)

        # 导入/导出按钮行
        io_frame = tk.Frame(self, bg=SIDEBAR_BG, padx=10)
        io_frame.pack(fill=tk.X, pady=(0, 6))
        io_frame.grid_columnconfigure(0, weight=1, uniform="project_io")
        io_frame.grid_columnconfigure(1, weight=1, uniform="project_io")
        import_btn = _make_btn(io_frame, "\U0001f4e5 导入项目", self._import_project, "ghost")
        export_btn = _make_btn(io_frame, "\U0001f4e4 导出项目", self._export_project, "ghost")
        import_btn.grid(row=0, column=0, sticky="ew", padx=(0, 4))
        export_btn.grid(row=0, column=1, sticky="ew")

        search_frame = tk.Frame(self, bg=SIDEBAR_BG, padx=10)
        search_frame.pack(fill=tk.X, pady=(0, 6))
        search_container = tk.Frame(search_frame, bg="white",
                                     highlightbackground=SIDEBAR_ITEM_BORDER,
                                     highlightthickness=1, bd=0)
        search_container.pack(fill=tk.X)
        icon_lbl = tk.Label(search_container, text="\U0001f50d", font=FONT_BODY,
                            bg="white", fg=TEXT_SECONDARY)
        icon_lbl.pack(side=tk.LEFT, padx=(8, 4), pady=4)
        self.search_var = tk.StringVar()
        self.search_var.trace_add("write", lambda *_: self._filter())
        # ttk.Entry 不支持 relief/borderwidth/bg；用 tk.Entry 实现白底无边框搜索框
        se = tk.Entry(search_container, textvariable=self.search_var,
                      font=FONT_BODY, relief="flat", borderwidth=0,
                      highlightthickness=0, bg="white", fg=TEXT_PRIMARY,
                      insertbackground=TEXT_PRIMARY)
        se.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 8), pady=4)

        # 分割线
        sep = tk.Frame(self, bg=SIDEBAR_ITEM_BORDER, height=1)
        sep.pack(fill=tk.X, padx=10, pady=(0, 4))

        list_frame = tk.Frame(self, bg=SIDEBAR_BG)
        list_frame.pack(fill=tk.BOTH, expand=True, padx=6)

        self.canvas = tk.Canvas(list_frame, borderwidth=0, highlightthickness=0, bg=SIDEBAR_BG)
        self.scrollbar = ttk.Scrollbar(list_frame, orient=tk.VERTICAL, command=self.canvas.yview)
        self.canvas.configure(yscrollcommand=self.scrollbar.set)
        self.items_frame = tk.Frame(self.canvas, bg=SIDEBAR_BG)
        self.canvas_win = self.canvas.create_window((0, 0), window=self.items_frame, anchor="nw")
        self.canvas.bind("<Configure>", self._on_canvas_configure)
        self.items_frame.bind("<Configure>", self._on_items_configure)
        self.canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        self.scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        self.items_frame.bind("<MouseWheel>", self._on_mousewheel)
        self.canvas.bind("<MouseWheel>", self._on_mousewheel)
        # 兜底支持 Linux/macOS（其滚轮事件不是 <MouseWheel>）
        self.items_frame.bind("<Button-4>", lambda e: self._scroll_units(-1))
        self.items_frame.bind("<Button-5>", lambda e: self._scroll_units(1))
        self.canvas.bind("<Button-4>", lambda e: self._scroll_units(-1))
        self.canvas.bind("<Button-5>", lambda e: self._scroll_units(1))

        # 记录 item 控件以便点击时只更新背景，不重建整列表
        self._item_widgets = {}

        # ── 底部设置入口（先 pack，BOTTOM 固定在底） ───────────
        bottom_frame = tk.Frame(self, bg=SIDEBAR_BG, padx=10, pady=10)
        bottom_frame.pack(side=tk.BOTTOM, fill=tk.X)
        _make_btn(bottom_frame, "\u2699\ufe0f 设置", self._open_settings, "ghost").pack(fill=tk.X)
        _make_btn(bottom_frame, "\u21bb 检查更新", self._check_update, "ghost").pack(fill=tk.X)

    def _on_canvas_configure(self, event=None):
        self.canvas.itemconfig(self.canvas_win, width=self.canvas.winfo_width())
        self._update_scrollregion()

    def _on_items_configure(self, event=None):
        self._update_scrollregion()

    def _update_scrollregion(self):
        """强制刷新 scrollregion，确保上下边界正确。"""
        self.canvas.update_idletasks()
        bbox = self.canvas.bbox("all")
        if bbox and bbox[3] > bbox[1]:
            self.canvas.configure(scrollregion=bbox)
        else:
            self.canvas.configure(scrollregion=(0, 0, self.canvas.winfo_width(), 0))

    def _scroll_units(self, units):
        """带边界检查的滚动，避免越界。"""
        if not self.canvas.winfo_exists():
            return
        # 如果内容未超出视口，不响应滚动
        sr = self.canvas.cget("scrollregion")
        try:
            x1, y1, x2, y2 = map(float, sr.split())
        except (ValueError, tk.TclError):
            return
        if y2 - y1 <= self.canvas.winfo_height():
            return
        scroll_canvas_units_clamped(self.canvas, units)

    def _on_mousewheel(self, event):
        # Windows / macOS：event.delta 是 120 的整数倍
        delta = -1 * (event.delta / 120)
        units = 1 if delta > 0 else -1 if delta < 0 else 0
        self._scroll_units(int(units * abs(delta)) or units)

    def _bind_mousewheel_recursive(self, widget):
        """让列表项及其所有子控件都能接收滚轮事件。"""
        widget.bind("<MouseWheel>", self._on_mousewheel)
        widget.bind("<Button-4>", lambda e: self._scroll_units(-1))
        widget.bind("<Button-5>", lambda e: self._scroll_units(1))
        for child in widget.winfo_children():
            self._bind_mousewheel_recursive(child)

    def refresh(self):
        # 记住当前选中以便重建后保持高亮
        prev_selected = self.selected_uuid
        for w in self.items_frame.winfo_children():
            w.destroy()
        self._item_widgets = {}
        projects = list_projects()
        query = self.search_var.get().strip().lower() if self.search_var.get() else ""
        filtered = [p for p in projects if not query or query in p.get("name", "").lower()]
        if not filtered:
            lbl = tk.Label(self.items_frame, text="暂无项目\n点击上方按钮创建",
                           bg=SIDEBAR_BG, fg=SIDEBAR_FG, font=FONT_BODY, pady=30)
            lbl.pack(fill=tk.X)
            self._update_scrollregion()
            return
        for p in filtered:
            self._add_item(p)
        # 刷新后重新计算滚动区
        self._update_scrollregion()
        # 滚回顶部
        self.canvas.yview_moveto(0)

    def _add_item(self, project):
        uuid = project["project_uuid"]
        name = project.get("name", "未命名")
        status = ProjectStatus.from_value(project.get("status"))
        is_selected = uuid == self.selected_uuid

        if is_selected:
            bg = SIDEBAR_SELECTED_BG
            fg = SIDEBAR_SELECTED_FG
            name_fg = SIDEBAR_SELECTED_FG
        else:
            bg = SIDEBAR_BG
            fg = SIDEBAR_FG
            name_fg = SIDEBAR_FG

        status_text = f"{status.icon} {status.display_name}"
        status_color = status.color

        item = tk.Frame(self.items_frame, bg=bg, cursor="hand2", padx=14, pady=12)
        item.pack(fill=tk.X, padx=8, pady=3)

        # 左侧选中指示条
        indicator = None
        if is_selected:
            indicator = tk.Frame(item, bg=ACCENT, width=4)
            indicator.pack(side=tk.LEFT, padx=(0, 10))

        name_frame = tk.Frame(item, bg=bg)
        name_frame.pack(fill=tk.X)
        name_lbl = tk.Label(name_frame, text=name, font=FONT_BODY_BOLD, bg=bg, fg=name_fg,
                            anchor="w")
        name_lbl.pack(side=tk.LEFT)
        status_lbl = tk.Label(name_frame, text=status_text, font=FONT_SMALL, bg=bg,
                              fg=status_color, anchor="w")
        status_lbl.pack(side=tk.RIGHT)

        # 让 item + 所有直接子控件都能用 as 列表统一处理
        all_widgets = [item, name_frame, name_lbl, status_lbl]
        if indicator is not None:
            all_widgets.append(indicator)

        def _set_item_bg(color, fg_color=None):
            item.config(bg=color)
            name_frame.config(bg=color)
            name_lbl.config(bg=color, fg=(fg_color or SIDEBAR_FG))
            status_lbl.config(bg=color)

        def on_click(e, u=uuid):
            self._set_selected(u)
            self.on_select(u)

        def on_right_click(e, u=uuid, p=project):
            self._show_context_menu(e, u, p)

        for w in all_widgets:
            w.bind("<Button-1>", on_click)
            w.bind("<Button-3>", on_right_click)
            if not is_selected:
                w.bind("<Enter>", lambda e, i=item: i.config(bg=SIDEBAR_HOVER))
                w.bind("<Leave>", lambda e, i=item, u=uuid:
                       i.config(bg=SIDEBAR_SELECTED_BG if u == self.selected_uuid else SIDEBAR_BG))

        # 让项目行上的所有子控件都能响应滚轮
        self._bind_mousewheel_recursive(item)

        # 注册到 _item_widgets，便于 _set_selected 局部更新
        self._item_widgets[uuid] = {
            "item": item,
            "name_frame": name_frame,
            "name_lbl": name_lbl,
            "status_lbl": status_lbl,
            "indicator": indicator,
            "_set_item_bg": _set_item_bg,
            "name": name,
            "status": status,
        }

    def _set_selected(self, new_uuid):
        """只更新选中项的视觉，不重建整列表，避免闪烁和卡顿。"""
        if self.selected_uuid == new_uuid:
            return
        old_uuid = self.selected_uuid
        self.selected_uuid = new_uuid

        if old_uuid in self._item_widgets:
            w = self._item_widgets[old_uuid]
            w["_set_item_bg"](SIDEBAR_BG, SIDEBAR_FG)
            if w["indicator"] is not None:
                w["indicator"].destroy()
                w["indicator"] = None

        if new_uuid in self._item_widgets:
            w = self._item_widgets[new_uuid]
            w["_set_item_bg"](SIDEBAR_SELECTED_BG, SIDEBAR_SELECTED_FG)
            indicator = tk.Frame(w["item"], bg=ACCENT, width=4)
            indicator.pack(side=tk.LEFT, padx=(0, 10))
            w["indicator"] = indicator
            # 给 indicator 重新绑定滚轮和点击
            self._bind_mousewheel_recursive(indicator)
            indicator.bind("<Button-1>",
                           lambda e, u=new_uuid: (self._set_selected(u), self.on_select(u)))
            indicator.bind("<Button-3>",
                           lambda e, u=new_uuid: self._show_context_menu(e, u))

    def _filter(self):
        self.refresh()

    def _show_context_menu(self, event, uuid, project=None):
        """显示项目右键菜单。"""
        project = self._project_for_context_menu(uuid, project)
        if project is None:
            return
        menu = tk.Menu(self, tearoff=0)
        # 新增：回滚存档入口（与导出/删除等并列）
        menu.add_command(
            label=self.ROLLBACK_MENU_LABEL,
            command=lambda: self._open_rollback_dialog(uuid),
            state=self._project_rollback_menu_state(project),
        )
        menu.add_separator()
        menu.add_command(label="\U0001f5c2\ufe0f 打开文件位置", command=lambda: self._open_file_location(uuid))
        menu.add_separator()
        # 已完成项目禁止删除（与 EditabilityPolicy 联动）
        delete_state = self._project_delete_menu_state(project)
        menu.add_command(
            label="\U0001f5d1\ufe0f 删除项目",
            command=lambda: self._delete_project(uuid, project),
            state=delete_state,
        )
        menu.tk_popup(event.x_root, event.y_root)

    def _project_for_context_menu(self, uuid, project=None):
        if project is None:
            for p in list_projects():
                if p["project_uuid"] == uuid:
                    project = p
                    break
        if project is None:
            return None
        live = self._item_widgets.get(uuid, {})
        live_status = live.get("status")
        if live_status is None:
            return project
        result = project.to_dict() if hasattr(project, "to_dict") else dict(project)
        result["status"] = ProjectStatus.from_value(live_status).value
        return result

    def _project_delete_menu_state(self, project: dict) -> str:
        project_status = ProjectStatus.from_value((project or {}).get("status"))
        if project_status == ProjectStatus.DONE:
            return "disabled"
        return "normal"

    def _project_rollback_menu_state(self, project: dict) -> str:
        project_status = ProjectStatus.from_value((project or {}).get("status"))
        if project_status == ProjectStatus.DONE:
            return "disabled"
        return "normal"

    def _open_rollback_dialog(self, uuid: str):
        """打开回滚存档弹窗。"""
        from .dialogs.rollback import RollbackDialog
        dlg = RollbackDialog(self.winfo_toplevel(), uuid, on_rollback=self._on_rollback_done)
        self.wait_window(dlg.dialog)

    @staticmethod
    def _confirm_delete(parent, title: str, message: str) -> bool:
        from .widgets.confirm_dialog import confirm_dialog
        return confirm_dialog(parent, title, message)

    def _on_rollback_done(self, uuid: str):
        """回滚完成后：刷新侧边栏 + 重新加载项目。"""
        self.refresh()
        self.on_select(uuid)

    def update_item_name(self, uuid: str, new_name: str) -> None:
        """就地更新项目列表中某项的名称标签（不重建列表，避免闪烁）。"""
        w = self._item_widgets.get(uuid)
        if w is None:
            return
        w["name"] = new_name
        try:
            w["name_lbl"].config(text=new_name)
        except tk.TclError:
            pass

    def update_item_status(self, uuid: str, status) -> None:
        """就地更新项目列表中某项的状态标签（不重建列表，避免闪烁）。

        status 可以是 ProjectStatus 枚举、字符串 ("editing"/"done"/"active"/"completed")。
        """
        ps = ProjectStatus.from_value(status)
        w = self._item_widgets.get(uuid)
        if w is None:
            return
        w["status"] = ps.value
        try:
            w["status_lbl"].config(text=f"{ps.icon} {ps.display_name}", fg=ps.color)
        except tk.TclError:
            pass

    def _delete_project(self, uuid, project):
        project = self._project_for_context_menu(uuid, project)
        if project is None:
            return
        # 防御层：DONE 状态即使通过 lambda/键盘等路径触达此处也拒绝
        if self._project_delete_menu_state(project) == "disabled":
            return
        name = project.get("name", "未命名")
        if self._confirm_delete(
            self.winfo_toplevel(),
            "确认删除",
            f"确定要删除项目「{name}」吗？\n\n此操作不可恢复，项目的所有数据将被永久删除。",
        ):
            if delete_project(uuid):
                if self.selected_uuid == uuid:
                    self.selected_uuid = None
                    self.on_select(None)
                self.refresh()
            else:
                messagebox.showerror("错误", "删除项目失败")

    def _open_file_location(self, uuid):
        """在系统文件管理器中打开项目文件所在目录并选中该文件。"""
        file_path = str(project_file_path(uuid))
        file_path = os.path.normpath(file_path)
        if not os.path.isfile(file_path):
            messagebox.showerror("错误", f"项目文件不存在：\n{file_path}", parent=self)
            return
        try:
            if sys.platform.startswith("win"):
                # Windows: 打开 explorer 并选中目标文件
                subprocess.Popen(["explorer", f"/select,{file_path}"])
            elif sys.platform == "darwin":
                subprocess.Popen(["open", "-R", file_path])
            else:
                subprocess.Popen(["xdg-open", PROJECTS_DIR])
        except Exception as e:
            # 兜底：至少打开所在目录
            try:
                if sys.platform.startswith("win"):
                    os.startfile(PROJECTS_DIR)  # noqa: S606
                else:
                    subprocess.Popen(["xdg-open", PROJECTS_DIR])
            except Exception as e2:
                messagebox.showerror("错误", f"无法打开文件位置：\n{e2}", parent=self)

    def _new_project(self):
        NewProjectDialog(self.winfo_toplevel(), self.refresh)

    def _open_settings(self):
        from .dialogs.settings import SettingsDialog
        from ..voice import get_voice
        get_voice().stop()
        SettingsDialog(self.winfo_toplevel())
        if self._on_settings_closed:
            self._on_settings_closed()

    def _check_update(self):
        from ..updater import check_for_update, UpdateChecker
        from .dialogs.update_dialog import UpdateDialog
        checker = UpdateChecker()
        info = check_for_update()
        if info is None:
            from tkinter import messagebox
            messagebox.showinfo("检查更新", "当前已是最新版本。", parent=self)
        else:
            UpdateDialog(self.winfo_toplevel(), info)

    def _export_project(self):
        if not self.selected_uuid:
            messagebox.showinfo("提示", "请先选择一个项目")
            return
        projects = list_projects()
        project = next((p for p in projects if p["project_uuid"] == self.selected_uuid), None)
        if not project:
            messagebox.showerror("错误", "找不到项目数据")
            return
        name = project.get("name", "项目")
        path = filedialog.asksaveasfilename(
            defaultextension=".json",
            filetypes=[("JSON文件", "*.json"), ("所有文件", "*.*")],
            title="导出项目",
            initialfile=f"{name}.json",
            parent=self,
        )
        if not path:
            return
        if export_project(self.selected_uuid, path):
            messagebox.showinfo("成功", f"项目已导出到：\n{path}", parent=self)
        else:
            messagebox.showerror("错误", "导出失败", parent=self)

    def _import_project(self):
        path = filedialog.askopenfilename(
            filetypes=[("JSON文件", "*.json"), ("所有文件", "*.*")],
            title="导入项目",
            parent=self,
        )
        if not path:
            return
        try:
            project = import_project(path)
            if project:
                # 导入后复制原项目的数据到新项目
                from ..project_manager import get_project, update_project
                new_uuid = project["project_uuid"]
                new_data = get_project(new_uuid)
                with open(path, encoding="utf-8") as f:
                    import json
                    imported = json.load(f)
                # 复制账单、工种、分类等数据
                for key in ["trade_items", "bills", "category_order"]:
                    if key in imported:
                        new_data[key] = imported[key]
                update_project(new_uuid, new_data)
                self.selected_uuid = new_uuid
                self.on_select(new_uuid)
                self.refresh()
                messagebox.showinfo("成功", f"项目已导入：{new_data.get('name', '')}", parent=self)
        except Exception as e:
            messagebox.showerror("错误", f"导入失败：{e}", parent=self)
