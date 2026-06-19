"""主窗口组装"""
import tkinter as tk
from tkinter import ttk

from .theme import (
    APP_BG, SIDEBAR_BG,
)
from .font_manager import font_manager
from .sidebar import Sidebar
from .content import ContentArea
from .editability import EditabilityPolicy
from .widgets import DraggableSplitter, TooltipCarousel
from ..config_loader import load_app, save_app
from ..logger import logger
from ..voice import get_voice


class MainInterface:
    WINDOW_KEY = "main"

    def __init__(self, root):
        self.root = root
        self.root.title("施工项目记账程序")
        self.root.configure(bg=APP_BG)
        self.root.minsize(1000, 650)

        # Initialize font manager BEFORE any widget construction
        font_manager.init(root)

        self._apply_window_geometry()
        self._apply_styles()

        # ── 主布局容器 ──
        self._main_frame = tk.Frame(root, bg=APP_BG)
        self._main_frame.pack(fill=tk.BOTH, expand=True)

        # 计算初始 sidebar 宽度（从 app_config 读取归一化比例）
        ratio = load_app().get("sidebar_width_ratio", 0.2)
        ww = max(self.root.winfo_width(), 800)
        raw_w = int(ww * ratio)
        self._sidebar_width = max(200, min(900, raw_w))
        logger.debug("[sidebar] init: ratio=%.6f win_width=%s raw_px=%s clamped_px=%s",
                     ratio, ww, raw_w, self._sidebar_width)

        self.sidebar = Sidebar(
            self._main_frame, self._on_project_select,
            editability=None,
            on_settings_closed=self._on_settings_closed,
        )
        self.sidebar.configure(width=self._sidebar_width)
        self.sidebar.pack(side=tk.LEFT, fill=tk.Y)
        self.sidebar.pack_propagate(False)

        self._splitter = DraggableSplitter(
            self._main_frame, self.sidebar,
            min_width=200, max_width=900,
            on_resize=self._on_sidebar_resize,
            default_width=self._sidebar_width,
            bg=SIDEBAR_BG,
            name="sidebar",
            ref_widget=self.root,
        )
        self._splitter.pack(side=tk.LEFT, fill=tk.Y)

        # ── 右侧区域：content + tooltip 上下排布 ──
        self._right_frame = tk.Frame(self._main_frame, bg=APP_BG)
        self._right_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        # 提示条（先 pack 在 right_frame 底部）
        _tc_cfg = load_app().get("tooltips", {})
        self._tooltip = TooltipCarousel(
            self._right_frame,
            messages=_tc_cfg.get("messages", ["双击行可编辑；拖表头竖条可调列宽"]),
            prefix=_tc_cfg.get("prefix", "◆ "),
            dwell_per_char_ms=_tc_cfg.get("dwell_per_char_ms", 80),
            font_size=_tc_cfg.get("font_size", 13),
            anchor="center",
        )
        self._tooltip.pack(side=tk.BOTTOM, fill=tk.X)

        self.content = ContentArea(
            self._right_frame,
            on_name_change=self._on_project_name_change,
            on_status_change=self._on_project_status_change,
        )
        self.content.pack(fill=tk.BOTH, expand=True)
        logger.debug("MainInterface: ContentArea created, packed expand=True")

        self.editability = EditabilityPolicy(
            get_current_status=self.content.get_project_status,
            current_uuid_provider=lambda: self.content.current_uuid or "",
        )
        self.content.set_editability(self.editability)
        self.sidebar._editability = self.editability

        self._bind_shortcuts()
        self._bind_window_events()
        self._schedule_update_check()
        self.root.after_idle(self._log_layout_state)

    def _log_layout_state(self) -> None:
        """启动后输出布局实测数据，用于排查宽度问题。"""
        try:
            win_w = self.root.winfo_width()
            frame_w = self._main_frame.winfo_width()
            side_w = self.sidebar.winfo_width()
            split_w = self._splitter.winfo_width()
            content_w = self.content.winfo_width()
            logger.debug(
                "[layout] win=%s frame=%s | sidebar=%s splitter=%s content=%s sum=%s",
                win_w, frame_w, side_w, split_w, content_w,
                side_w + split_w + content_w,
            )
        except tk.TclError:
            pass

    def _on_sidebar_resize(self, width: int) -> None:
        """DraggableSplitter 释放时回调：保存归一化宽度比例到 app_config。"""
        try:
            win_w = self.root.winfo_width()
            frame_w = self._main_frame.winfo_width()
            ratio = round(width / max(win_w, 1), 6)
            logger.debug("[sidebar] save: width=%s win_width=%s frame_width=%s ratio=%.6f",
                         width, win_w, frame_w, ratio)
            cfg = load_app()
            old = cfg.get("sidebar_width_ratio", 0)
            if abs(old - ratio) > 1e-6:
                cfg["sidebar_width_ratio"] = ratio
                save_app(cfg)
                logger.debug("[sidebar] saved: %.6f -> %.6f", old, ratio)
            else:
                logger.debug("[sidebar] unchanged: ratio=%.6f", ratio)
        except Exception as e:
            logger.error("[sidebar] save failed: %s", e, exc_info=True)

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
            logger.debug("[win_geom] saving: %dx%d cat_ratio=%s",
                         w, h, cfg.get("category_list_width_ratio", "<absent>"))
            try:
                save_app(cfg)
            except Exception:
                pass
        else:
            logger.debug("[win_geom] unchanged: %dx%d", w, h)

    def _bind_window_events(self):
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)
        self.root.bind("<Configure>", self._on_configure)

    def _on_configure(self, event):
        if event.widget is not self.root:
            return
        logger.debug("[win_geom] Configure event: %dx%d, debounce 200ms",
                     event.width, event.height)
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
        from .shortcut_manager import shortcut_manager
        shortcut_manager.init(self)
        shortcut_manager.bind_all_shortcuts(self.root)

    def _apply_styles(self):
        s = ttk.Style()
        s.theme_use("clam")
        s.configure("TCombobox", font=font_manager.get("body"))
        s.configure("TEntry", font=font_manager.get("body"))
        s.configure("Treeview", font=font_manager.get("tree"), rowheight=44)
        s.configure("Treeview.Heading", font=font_manager.get("tree_header"))

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

