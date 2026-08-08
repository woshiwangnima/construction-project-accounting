"""Settings dialog with pluggable panels.

To add a new settings panel:
    1. Create a file in this package (e.g. font_panel.py)
    2. Define a BaseSettingsPanel subclass with the @register_section decorator
    3. Add an import below (one line, for registration side-effect)
    4. The dialog will pick it up automatically
"""

import tkinter as tk

from ...theme import (
    APP_BG, ACCENT, ICON_BTN_HOVER, SEPARATOR, SIDEBAR_BG, SIDEBAR_FG, TEXT_PRIMARY,
)
from ...font_manager import font_manager
from ....logger import logger
from .base import BaseSettingsPanel, get_sections

# Trigger panel registration via the @register_section decorator.
from . import basic_panel  # noqa: F401
from . import font_panel  # noqa: F401
from . import shortcut_panel  # noqa: F401
from . import voice_panel  # noqa: F401
from . import export_panel  # noqa: F401
from . import about_panel  # noqa: F401
from . import notification_panel  # noqa: F401
from .basic_panel import BasicSettingsPanel  # noqa: F401
from .font_panel import FontSettingsPanel  # noqa: F401
from .shortcut_panel import ShortcutSettingsPanel  # noqa: F401
from .voice_panel import VoiceSettingsPanel  # noqa: F401
from .export_panel import ExportSettingsPanel  # noqa: F401
from .about_panel import AboutSettingsPanel  # noqa: F401


_NAV_WIDTH = 160
_DEFAULT_SETTINGS_SIZE = (900, 700)
_MIN_SETTINGS_SIZE = (700, 500)
_SAVE_RESIZE_DEBOUNCE_MS = 300


def _clamp_settings_size(value) -> tuple[int, int] | None:
    if not isinstance(value, (list, tuple)) or len(value) != 2:
        return None
    try:
        return (
            max(_MIN_SETTINGS_SIZE[0], int(value[0])),
            max(_MIN_SETTINGS_SIZE[1], int(value[1])),
        )
    except (TypeError, ValueError):
        return None


def _resolve_settings_size() -> tuple[int, int]:
    """读取设置窗口尺寸：user_config 优先 → app_config → 硬编码默认。"""
    try:
        from ....config_loader import load_user, load_app
        user_size = load_user().get("window_sizes", {}).get("settings")
        normalized = _clamp_settings_size(user_size)
        if normalized:
            return normalized
    except Exception:
        pass
    try:
        from ....config_loader import load_app
        app_size = load_app().get("window_sizes", {}).get("settings")
        normalized = _clamp_settings_size(app_size)
        if normalized:
            return normalized
    except Exception:
        pass
    return _DEFAULT_SETTINGS_SIZE


def _save_settings_size(w: int, h: int) -> None:
    """把用户调整后的尺寸写入 user_config。"""
    try:
        from ....config_loader import load_user, save_user
        cfg = load_user()
        sizes = cfg.setdefault("window_sizes", {})
        sizes["settings"] = [int(w), int(h)]
        save_user(cfg)
    except Exception as e:
        logger.warning("保存设置窗口尺寸失败: %s", e)


class SettingsDialog:
    """Settings window: left nav + right content panel.

    Sections are auto-discovered via the @register_section decorator.

    尺寸优先级：user_config 覆盖 > app_config 默认 > 硬编码默认。
    用户调整后通过 <Configure> 防抖 + 关闭时双写回 user_config。
    """

    def __init__(self, parent, on_close=None):
        dialog = tk.Toplevel(parent)
        self._dialog = dialog
        self._closed = False
        self._on_close_callback = on_close
        dialog.title("设置")
        dialog.transient(parent)
        dialog.grab_set()
        dialog.configure(bg=APP_BG)
        dialog.minsize(*_MIN_SETTINGS_SIZE)

        w, h = _resolve_settings_size()
        x = parent.winfo_rootx() + (parent.winfo_width() - w) // 2
        y = parent.winfo_rooty() + (parent.winfo_height() - h) // 2
        dialog.geometry(f"{w}x{h}+{x}+{y}")

        self._build_title(dialog)
        tk.Frame(dialog, bg=SEPARATOR, height=1).pack(fill=tk.X)
        self._build_main(dialog)
        self._load_nav(dialog)

        # 跟踪用户调整的尺寸（防抖写回 user_config）
        self._save_size_after_id: str | None = None
        self._initial_size = (w, h)
        self._last_saved_size = self._initial_size
        self._last_configured_size = self._initial_size
        dialog.bind("<Configure>", self._on_configure)

        dialog.protocol("WM_DELETE_WINDOW", lambda: self._on_close(dialog))

        sections = get_sections()
        if sections:
            self._show_section(sections[0])

    def _on_configure(self, event):
        """窗口尺寸变化时防抖写回 user_config（不区分根还是子 widget）。"""
        if self._closed or event.widget is not self._dialog:
            return
        size = (getattr(event, "width", 0), getattr(event, "height", 0))
        if size[0] <= 0 or size[1] <= 0 or size == self._last_configured_size:
            return
        self._last_configured_size = size
        if self._save_size_after_id is not None:
            try:
                self._dialog.after_cancel(self._save_size_after_id)
            except tk.TclError:
                pass
        self._save_size_after_id = self._dialog.after(
            _SAVE_RESIZE_DEBOUNCE_MS, self._save_size_now
        )

    def _save_size_now(self):
        self._save_size_after_id = None
        if not self._dialog.winfo_exists():
            return
        w = self._dialog.winfo_width()
        h = self._dialog.winfo_height()
        if w < _MIN_SETTINGS_SIZE[0] or h < _MIN_SETTINGS_SIZE[1]:
            return
        if (w, h) == self._last_saved_size:
            return
        _save_settings_size(w, h)
        self._last_saved_size = (w, h)

    def _build_title(self, dialog):
        title_bar = tk.Frame(dialog, bg=APP_BG, height=48)
        title_bar.pack(fill=tk.X)
        title_bar.pack_propagate(False)
        tk.Label(title_bar, text="⚙ 设置", font=font_manager.get("heading"),
                 bg=APP_BG, fg=TEXT_PRIMARY).pack(side=tk.LEFT, padx=20)

    def _build_main(self, dialog):
        main = tk.Frame(dialog, bg=APP_BG)
        main.pack(fill=tk.BOTH, expand=True)

        nav = tk.Frame(main, bg=SIDEBAR_BG, width=_NAV_WIDTH)
        nav.pack(side=tk.LEFT, fill=tk.Y)
        nav.pack_propagate(False)
        self._nav = nav

        self._content = tk.Frame(main, bg=APP_BG)
        self._content.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

    def _load_nav(self, dialog):
        self._sections = get_sections()
        self._current_panel: BaseSettingsPanel | None = None
        # 设置面板首次访问时才创建；切换后保留实例，避免重复执行
        # _build() / _load()（字体面板还会枚举系统字体并创建大量控件）。
        self._panel_cache: dict[type[BaseSettingsPanel], BaseSettingsPanel] = {}
        self._nav_buttons: list[tk.Button] = []
        self._nav_selected_font = font_manager.get("entry_item").copy()
        self._nav_selected_font.configure(slant="italic")
        self._nav_normal_font = font_manager.get("entry_item")

        for sec in self._sections:
            btn = tk.Button(
                self._nav,
                text=f"  {sec.section_icon}  {sec.section_title}",
                font=self._nav_normal_font, bg=SIDEBAR_BG, fg=SIDEBAR_FG, bd=0,
                relief="flat", anchor="w", cursor="hand2",
                activebackground=ICON_BTN_HOVER, activeforeground=TEXT_PRIMARY,
                padx=12, pady=10,
                justify="left", wraplength=_NAV_WIDTH - 24,
                command=lambda s=sec: self._show_section(s),
            )
            btn.pack(fill=tk.X)
            self._nav_buttons.append(btn)

    def _show_section(self, section_cls):
        current = self._current_panel
        cached = self._panel_cache.get(section_cls)
        if cached is current and current is not None:
            # 重复点击当前导航项不触发保存、重排或重建。
            return

        if current is not None:
            # Do not synchronously write config from a navigation click.  The
            # panel is cached, so its debounced save remains alive while it is
            # hidden; close-time flush is still the final durability boundary.
            current.on_hide()
            current.pack_forget()

        self._update_nav_selection(section_cls)

        panel = self._panel_cache.get(section_cls)
        if panel is None:
            panel = section_cls(self._content)
            self._panel_cache[section_cls] = panel
        panel.pack(fill=tk.BOTH, expand=True, padx=20, pady=16)
        self._current_panel = panel

    def _update_nav_selection(self, section_cls):
        for btn, sec in zip(self._nav_buttons, self._sections):
            if sec is section_cls:
                btn.config(bg=ACCENT, fg="white", font=self._nav_selected_font)
            else:
                btn.config(bg=SIDEBAR_BG, fg=SIDEBAR_FG, font=self._nav_normal_font)

    def _on_close(self, dialog):
        if self._closed:
            return
        self._closed = True
        if self._save_size_after_id is not None:
            try:
                dialog.after_cancel(self._save_size_after_id)
            except tk.TclError:
                pass
            self._save_size_after_id = None
        for panel in self._panel_cache.values():
            panel.close()
        # 关闭时也存一次（防抖可能还没触发）
        self._save_size_now()
        dialog.destroy()
        callback = getattr(self, "_on_close_callback", None)
        if callable(callback):
            try:
                callback()
            except Exception as exc:  # pragma: no cover - callback boundary
                logger.warning("设置关闭回调执行失败: %s", exc)
