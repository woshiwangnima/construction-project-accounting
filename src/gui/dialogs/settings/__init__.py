"""Settings dialog with pluggable panels.

To add a new settings panel:
    1. Create a file in this package (e.g. font_panel.py)
    2. Define a BaseSettingsPanel subclass with the @register_section decorator
    3. Add an import below (one line, for registration side-effect)
    4. The dialog will pick it up automatically
"""

import tkinter as tk

from ...theme import (
    APP_BG, ACCENT, SIDEBAR_BG, SIDEBAR_FG, TEXT_PRIMARY,
    FONT_HEADING, FONT_BODY,
)
from ....logger import logger
from .base import BaseSettingsPanel, get_sections

# Trigger panel registration via the @register_section decorator.
from . import basic_panel  # noqa: F401
from . import voice_panel  # noqa: F401
from . import export_panel  # noqa: F401
from . import about_panel  # noqa: F401
from .basic_panel import BasicSettingsPanel  # noqa: F401
from .voice_panel import VoiceSettingsPanel  # noqa: F401
from .export_panel import ExportSettingsPanel  # noqa: F401
from .about_panel import AboutSettingsPanel  # noqa: F401


_NAV_WIDTH = 160
_DEFAULT_SETTINGS_SIZE = (900, 700)
_MIN_SETTINGS_SIZE = (700, 500)
_SAVE_RESIZE_DEBOUNCE_MS = 300


def _resolve_settings_size() -> tuple[int, int]:
    """读取设置窗口尺寸：user_config 优先 → app_config → 硬编码默认。"""
    try:
        from ....config_loader import load_user, load_app
        user_size = load_user().get("window_sizes", {}).get("settings")
        if user_size and isinstance(user_size, list) and len(user_size) == 2:
            return int(user_size[0]), int(user_size[1])
    except Exception:
        pass
    try:
        from ....config_loader import load_app
        app_size = load_app().get("window_sizes", {}).get("settings")
        if app_size and isinstance(app_size, list) and len(app_size) == 2:
            return int(app_size[0]), int(app_size[1])
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

    def __init__(self, parent):
        dialog = tk.Toplevel(parent)
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
        tk.Frame(dialog, bg="#e2e8f0", height=1).pack(fill=tk.X)
        self._build_main(dialog)
        self._load_nav(dialog)

        # 跟踪用户调整的尺寸（防抖写回 user_config）
        self._save_size_after_id: str | None = None
        self._initial_size = (w, h)
        dialog.bind("<Configure>", self._on_configure)

        dialog.protocol("WM_DELETE_WINDOW", lambda: self._on_close(dialog))
        self._dialog = dialog

        sections = get_sections()
        if sections:
            self._show_section(sections[0])

    def _on_configure(self, event):
        """窗口尺寸变化时防抖写回 user_config（不区分根还是子 widget）。"""
        if event.widget is not self._dialog:
            return
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
        if (w, h) == self._initial_size:
            return
        _save_settings_size(w, h)

    def _build_title(self, dialog):
        title_bar = tk.Frame(dialog, bg=APP_BG, height=48)
        title_bar.pack(fill=tk.X)
        title_bar.pack_propagate(False)
        tk.Label(title_bar, text="⚙ 设置", font=FONT_HEADING,
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
        self._nav_buttons: list[tk.Button] = []

        for sec in self._sections:
            btn = tk.Button(
                self._nav,
                text=f"  {sec.section_icon}  {sec.section_title}",
                font=FONT_BODY, bg=SIDEBAR_BG, fg=SIDEBAR_FG, bd=0,
                relief="flat", anchor="w", cursor="hand2",
                activebackground="#e2e8f0", activeforeground=TEXT_PRIMARY,
                padx=12, pady=10,
                command=lambda s=sec: self._show_section(s),
            )
            btn.pack(fill=tk.X)
            self._nav_buttons.append(btn)

    def _show_section(self, section_cls):
        if self._current_panel is not None:
            self._current_panel.flush_pending()
            self._current_panel.destroy()

        for btn, sec in zip(self._nav_buttons, self._sections):
            if sec is section_cls:
                btn.config(bg=ACCENT, fg="white")
            else:
                btn.config(bg=SIDEBAR_BG, fg=SIDEBAR_FG)

        self._current_panel = section_cls(self._content)
        self._current_panel.pack(fill=tk.BOTH, expand=True, padx=20, pady=16)

    def _on_close(self, dialog):
        if self._current_panel is not None:
            self._current_panel.flush_pending()
        # 关闭时也存一次（防抖可能还没触发）
        self._save_size_now()
        dialog.destroy()
