"""主窗口组装"""
import tkinter as tk
from tkinter import ttk

from .theme import (
    APP_BG, FONT_BODY, FONT_TREE, FONT_TREE_HEADER,
)
from .sidebar import Sidebar
from .content import ContentArea
from .editability import EditabilityPolicy
from ..config_loader import load_app, save_app, load_user, save_user
from ..logger import logger
from ..voice import get_voice


class MainInterface:
    WINDOW_KEY = "main"

    def __init__(self, root):
        self.root = root
        self.root.title("施工项目记账程序")
        self.root.configure(bg=APP_BG)
        self.root.minsize(1000, 650)

        self._apply_window_geometry()
        self._apply_styles()

        self._main_pane = ttk.PanedWindow(root, orient=tk.HORIZONTAL)
        logger.debug("MainInterface: PanedWindow created, parent=root")
        self._main_pane.pack(fill=tk.BOTH, expand=True)
        logger.debug("MainInterface: PanedWindow packed fill=BOTH expand=True")

        self.content = ContentArea(
            self._main_pane,
            on_name_change=self._on_project_name_change,
            on_status_change=self._on_project_status_change,
        )
        logger.debug("MainInterface: ContentArea created, parent=_main_pane")

        self.editability = EditabilityPolicy(
            get_current_status=self.content.get_project_status,
            current_uuid_provider=lambda: self.content.current_uuid or "",
        )
        self.content.set_editability(self.editability)

        self.sidebar = Sidebar(
            self._main_pane, self._on_project_select,
            editability=self.editability,
            on_settings_closed=self._on_settings_closed,
        )
        logger.debug("MainInterface: Sidebar created, parent=_main_pane")
        self._main_pane.add(self.sidebar, weight=0)
        self._main_pane.add(self.content, weight=1)
        logger.debug("MainInterface: PanedWindow add sidebar+content done")

        # Track sidebar width changes via Configure event
        # (fires on sash drag, window resize, any layout change)
        self._sidebar_save_after_id = None
        self.sidebar.bind("<Configure>", self._on_sidebar_configure)
        logger.debug("MainInterface: sidebar <Configure> bound")

        self._bind_shortcuts()
        self._bind_window_events()
        self._schedule_update_check()
        self.root.after_idle(self._apply_sidebar_width)

    def _on_sidebar_configure(self, event):
        if event.widget is not self.sidebar:
            return
        logger.debug("_on_sidebar_configure: sidebar width=%s", event.width)
        if self._sidebar_save_after_id:
            try:
                self.root.after_cancel(self._sidebar_save_after_id)
            except tk.TclError:
                pass
        self._sidebar_save_after_id = self.root.after(
            500, self._debounced_save_sidebar_width
        )

    def _debounced_save_sidebar_width(self):
        self._sidebar_save_after_id = None
        try:
            width = self.sidebar.winfo_width()
            if width >= 100:
                logger.debug("save_sidebar: width=%s", width)
                self._save_sidebar_width(width)
        except tk.TclError:
            pass

    def _apply_window_geometry(self):
        cfg = load_app()
        sizes = cfg.setdefault("window_sizes", {})
        saved = sizes.get(self.WINDOW_KEY)

        try:
            self.root.state("zoomed")
        except tk.TclError:
            sw = self.root.winfo_screenwidth()
            sh = self.root.winfo_screenheight()
            self.root.geometry(f"{sw}x{sh}+0+0")
        self.root.update_idletasks()

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

        cur = [self.root.winfo_width(), self.root.winfo_height()]
        if cur[0] > 0 and cur[1] > 0 and sizes.get(self.WINDOW_KEY) != cur:
            sizes[self.WINDOW_KEY] = cur
            save_app(cfg)

    def _save_window_geometry(self):
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
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)
        self.root.bind("<Configure>", self._on_configure)

    def _on_configure(self, event):
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
        self.root.bind("<Control-n>", lambda e: self.sidebar._new_project())
        self.root.bind("<Control-N>", lambda e: self.sidebar._new_project())
        self.root.bind("<Delete>", lambda e: self._on_delete_key())
        self.root.bind("<F2>", lambda e: self._on_edit_key())

    def _on_delete_key(self):
        if self.content.tab_var.get() == "bills" and hasattr(self.content, '_render_bills'):
            pass
        elif self.content.tab_var.get() == "workers":
            self.content._delete_selected_item()

    def _on_edit_key(self):
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
        try:
            self.sidebar.update_item_status(uuid, new_status)
        except Exception:
            pass

    def _save_sidebar_width(self, width):
        try:
            cfg = load_user()
            ratio = round(width / max(self.root.winfo_width(), 1), 6)
            cfg["sidebar_width_ratio"] = ratio
            save_user(cfg)
            logger.debug("save_sidebar: saved ratio=%s (width=%s win=%s) to user_config",
                         ratio, width, self.root.winfo_width())
        except Exception:
            pass

    def _apply_sidebar_width(self):
        try:
            ratio = load_user().get("sidebar_width_ratio",
                                    load_app().get("sidebar_width_ratio", 0.2))
            ww = max(self.root.winfo_width(), 800)
            width = int(ww * ratio)
            width = max(200, min(900, width))
            logger.debug("apply_sidebar: ratio=%s win_width=%s -> width=%s",
                         ratio, ww, width)
            self._main_pane.sashpos(0, width)
            logger.debug("apply_sidebar: sashpos set OK")
        except Exception as e:
            logger.warning("apply_sidebar failed: %s", e, exc_info=True)
