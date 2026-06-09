"""主窗口组装"""
import tkinter as tk
from tkinter import ttk

from .theme import (
    APP_BG, SIDEBAR_ITEM_BORDER,
    FONT_BODY, FONT_TREE, FONT_TREE_HEADER,
)
from .sidebar import Sidebar
from .content import ContentArea
from .editability import EditabilityPolicy
from ..config_loader import load_app, save_app
from ..voice import get_voice


class MainInterface:
    WINDOW_KEY = "main"

    def __init__(self, root):
        self.root = root
        self.root.title("施工项目记账程序")
        self.root.configure(bg=APP_BG)
        self.root.minsize(1000, 650)

        # 默认全屏打开；窗口尺寸/位置记入 app_config.json::window_sizes
        self._apply_window_geometry()

        self._apply_styles()

        # ── 顺序：先建 ContentArea（policy 需要它的 get_project_status）──
        self.content = ContentArea(
            root,
            on_name_change=self._on_project_name_change,
            on_status_change=self._on_project_status_change,
        )
        # ── 全局唯一的 EditabilityPolicy：状态切换 / 切换项目时自动反映 ──
        self.editability = EditabilityPolicy(
            get_current_status=self.content.get_project_status,
            current_uuid_provider=lambda: self.content.current_uuid or "",
        )
        self.content.set_editability(self.editability)

        self.sidebar = Sidebar(
            root, self._on_project_select,
            editability=self.editability,
            on_settings_closed=self._on_settings_closed,
        )
        self.sidebar.pack(side=tk.LEFT, fill=tk.Y)

        sep = tk.Frame(root, bg=SIDEBAR_ITEM_BORDER, width=2)
        sep.pack(side=tk.LEFT, fill=tk.Y)

        self.content.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        self._bind_shortcuts()
        self._bind_window_events()
        self._schedule_update_check()

    def _apply_window_geometry(self):
        """根据配置决定全屏/自定义尺寸，并按需居中。"""
        cfg = load_app()
        sizes = cfg.setdefault("window_sizes", {})
        saved = sizes.get(self.WINDOW_KEY)

        # 默认全屏：先 zoom
        try:
            self.root.state("zoomed")
        except tk.TclError:
            # 非 Windows 平台 / 不支持 zoomed 时退化为屏幕尺寸
            sw = self.root.winfo_screenwidth()
            sh = self.root.winfo_screenheight()
            self.root.geometry(f"{sw}x{sh}+0+0")
        self.root.update_idletasks()

        # 只有当用户上次明确自定义过尺寸（与屏幕尺寸不一致）才还原
        if saved and isinstance(saved, list) and len(saved) == 2:
            w, h = int(saved[0]), int(saved[1])
            sw = self.root.winfo_screenwidth()
            sh = self.root.winfo_screenheight()
            if w > 200 and h > 200 and (w, h) != (sw, sh):
                w = min(w, sw)
                h = min(h, sh)
                x = max(0, (sw - w) // 2)
                y = max(0, (sh - h) // 2)
                self.root.geometry(f"{w}x{h}+{x}+{y}")
                self.root.update_idletasks()

        # 初次记录当前几何尺寸
        cur = [self.root.winfo_width(), self.root.winfo_height()]
        if cur[0] > 0 and cur[1] > 0 and sizes.get(self.WINDOW_KEY) != cur:
            sizes[self.WINDOW_KEY] = cur
            save_app(cfg)

    def _save_window_geometry(self):
        """关闭或尺寸变化时将当前尺寸写回配置文件。"""
        try:
            self.root.update_idletasks()
        except tk.TclError:
            return
        w, h = self.root.winfo_width(), self.root.winfo_height()
        if w < 200 or h < 200:
            return
        cfg = load_app()
        sizes = cfg.setdefault("window_sizes", {})
        if sizes.get(self.WINDOW_KEY) != [w, h]:
            sizes[self.WINDOW_KEY] = [w, h]
            try:
                save_app(cfg)
            except Exception:
                pass

    def _bind_window_events(self):
        """绑定关闭与尺寸变化事件，触发尺寸保存。"""
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)
        self.root.bind("<Configure>", self._on_configure)

    def _on_configure(self, event):
        """窗口几何变化时记录尺寸（去抖：200ms 内只写一次）。"""
        if event.widget is not self.root:
            return
        if getattr(self, "_save_after_id", None):
            try:
                self.root.after_cancel(self._save_after_id)
            except tk.TclError:
                pass
        self._save_after_id = self.root.after(200, self._save_window_geometry)

    def _on_close(self):
        self._save_window_geometry()
        self.root.destroy()

    def _bind_shortcuts(self):
        """绑定全局键盘快捷键"""
        self.root.bind("<Control-n>", lambda e: self.sidebar._new_project())
        self.root.bind("<Control-N>", lambda e: self.sidebar._new_project())
        self.root.bind("<Delete>", lambda e: self._on_delete_key())
        self.root.bind("<F2>", lambda e: self._on_edit_key())

    def _on_delete_key(self):
        """Delete 键删除当前选中的记录"""
        if self.content.tab_var.get() == "bills" and hasattr(self.content, '_render_bills'):
            # 账单管理 tab - 通过模拟删除按钮操作
            pass  # Treeview 会处理 Delete 键
        elif self.content.tab_var.get() == "workers":
            self.content._delete_selected_item()

    def _on_edit_key(self):
        """F2 键编辑当前选中的记录"""
        if self.content.tab_var.get() == "workers":
            self.content._edit_selected_item()

    def _apply_styles(self):
        s = ttk.Style()
        s.theme_use("clam")
        s.configure("TCombobox", font=FONT_BODY)
        s.configure("TEntry", font=FONT_BODY)
        s.configure("Treeview", font=FONT_TREE, rowheight=44)
        s.configure("Treeview.Heading", font=FONT_TREE_HEADER)

    def _on_project_select(self, uuid):
        self.content.load_project(uuid)

    def _on_project_name_change(self, uuid: str, new_name: str) -> None:
        """内容区项目名修改 → 同步更新侧边栏列表的同名标签（不重建列表）。"""
        try:
            self.sidebar.update_item_name(uuid, new_name)
        except Exception:
            pass

    def _on_settings_closed(self) -> None:
        get_voice().stop()
        self.content.refresh_app_settings()

    def _schedule_update_check(self):
        self.root.after(3000, self._do_update_check)

    def _do_update_check(self):
        try:
            from .dialogs.update_dialog import UpdateDialog
            from ..updater import UpdateChecker
            checker = UpdateChecker()
            checker.run_async()

            def _poll():
                if checker.is_done:
                    if checker.result:
                        UpdateDialog(self.root, checker.result)
                else:
                    self.root.after(500, _poll)
            self.root.after(500, _poll)
        except Exception as e:
            from ..logger import logger
            logger.warning("启动时检查更新失败: %s", e)

    def _on_project_status_change(self, uuid: str, new_status) -> None:
        """内容区项目状态切换 → 同步更新侧边栏列表的状态标签（不重建列表）。"""
        try:
            self.sidebar.update_item_status(uuid, new_status)
        except Exception:
            pass
