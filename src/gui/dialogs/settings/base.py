"""Settings panel base class and registry.

Use the @register_section decorator to register a panel.
SettingsDialog auto-discovers all registered sections via get_sections().
"""

import tkinter as tk
import re
from typing import ClassVar

from ...theme import APP_BG
from ....logger import logger


_SECTIONS: list[type["BaseSettingsPanel"]] = []
_HEX_COLOR_RE = re.compile(r"^#[0-9a-fA-F]{6}$")


def bind_responsive_wrap(
    widget: tk.Widget,
    container: tk.Widget,
    *,
    padding: int = 12,
    minimum: int = 160,
) -> None:
    """Keep a label/checkbutton readable as the settings pane is resized."""

    state = {
        "after_id": None,
        "last_width": None,
        "requested_width": None,
    }

    def read_width() -> int:
        return max(minimum, container.winfo_width() - padding)

    def apply():
        state["after_id"] = None
        try:
            width = state["requested_width"]
            state["requested_width"] = None
            if width is None:
                width = read_width()
            if width == state["last_width"]:
                return
            state["last_width"] = width
            widget.configure(wraplength=width)
        except tk.TclError:
            # The cached panel may be destroyed together with its dialog.
            return

    def update(_event=None):
        try:
            width = read_width()
            if width == state["last_width"]:
                state["requested_width"] = None
                return
            state["requested_width"] = width
            if state["after_id"] is None:
                state["after_id"] = container.after_idle(apply)
        except tk.TclError:
            # The cached panel may be destroyed together with its dialog.
            return

    container.bind("<Configure>", update, add="+")
    update()


def normalize_hex_color(value: object, fallback: str) -> str:
    """Return a canonical #RRGGBB value, falling back for invalid input."""

    color = str(value or "").strip()
    if _HEX_COLOR_RE.fullmatch(color):
        return color.lower()
    return fallback


class BaseSettingsPanel(tk.Frame):
    """Abstract base class for settings panels.

    Subclasses MUST define class attributes:
        section_id (str):    unique identifier (e.g. "voice")
        section_title (str): display name in left nav (e.g. "语音播报")
        section_icon (str):  emoji/icon shown in left nav (e.g. "🎙")
        section_order (int): sort order, lower numbers appear first (default 100)

    Subclasses MUST implement:
        _build(): create the panel UI widgets
        _load():  read current values from config into the UI
        _save():  write current UI values back to config

    Subclasses MAY call:
        _schedule_save() from a var trace to debounce auto-save
        flush_pending()  is used for the final close-time save
        on_hide()        is called when the user switches away from this panel
    """

    section_id: ClassVar[str] = ""
    section_title: ClassVar[str] = ""
    section_icon: ClassVar[str] = ""
    section_order: ClassVar[int] = 100

    def __init__(self, master, **kwargs):
        kwargs.setdefault("bg", APP_BG)
        super().__init__(master, **kwargs)
        self._save_after_id: str | None = None
        self._pending_save: bool = False
        self._closed: bool = False
        # _loading 标志：初始化阶段 _build → _load 期间，避免 var 写入触发自动保存
        self._loading: bool = True
        self._build()
        try:
            self._load()
        except Exception as e:
            logger.warning("设置面板加载失败 (%s): %s", self.section_id, e)
        finally:
            self._loading = False

    def _build(self) -> None:
        raise NotImplementedError

    def _load(self) -> None:
        raise NotImplementedError

    def _save(self) -> None:
        raise NotImplementedError

    def on_hide(self) -> None:
        """Handle leaving the panel without forcing a synchronous save.

        Panels remain cached while hidden, so their debounced save callback can
        finish normally.  The hook is intentionally a no-op for most panels;
        panels with transient UI state (such as voice preview) may override it.
        """
        return

    def _schedule_save(self) -> None:
        """Schedule a debounced auto-save (300ms). Safe to call from var traces."""
        if self._loading or self._closed:
            return
        if self._save_after_id is not None:
            try:
                self.after_cancel(self._save_after_id)
            except Exception:
                pass
        self._pending_save = True
        try:
            self._save_after_id = self.after(300, self._auto_save)
        except tk.TclError:
            self._save_after_id = None

    def _auto_save(self) -> None:
        if self._closed:
            self._save_after_id = None
            self._pending_save = False
            return
        self._save_after_id = None
        self._pending_save = False
        try:
            self._save()
        except Exception as e:
            logger.warning("设置自动保存失败 (%s): %s", self.section_id, e)

    def flush_pending(self) -> None:
        """Force-flush any pending debounced save. Called on panel switch / dialog close."""
        if self._save_after_id is not None:
            try:
                self.after_cancel(self._save_after_id)
            except Exception:
                pass
            self._save_after_id = None
        if not self._pending_save:
            return
        self._pending_save = False
        try:
            self._save()
        except Exception as e:
            logger.warning("设置保存失败 (%s): %s", self.section_id, e)

    def cancel_pending(self) -> None:
        """Discard a scheduled save, used by a panel's reset action."""
        if self._save_after_id is not None:
            try:
                self.after_cancel(self._save_after_id)
            except Exception:
                pass
            self._save_after_id = None
        self._pending_save = False

    def close(self) -> None:
        """Flush pending data, then stop callbacks for a cached panel."""
        if self._closed:
            return
        self.flush_pending()
        self._closed = True


def register_section(cls: type[BaseSettingsPanel]) -> type[BaseSettingsPanel]:
    """Class decorator: register a settings panel.

    Validates that the class has the required metadata, then adds it to the
    global registry. SettingsDialog picks it up via get_sections().
    """
    if not isinstance(cls, type) or not issubclass(cls, BaseSettingsPanel):
        raise TypeError(f"{cls!r} 必须继承 BaseSettingsPanel")
    for attr in ("section_id", "section_title", "section_icon"):
        if not getattr(cls, attr, ""):
            raise TypeError(f"{cls.__name__} 缺少类属性 {attr!r}")
    _SECTIONS.append(cls)
    return cls


def get_sections() -> list[type[BaseSettingsPanel]]:
    """Return all registered sections sorted by section_order."""
    return sorted(_SECTIONS, key=lambda c: c.section_order)


def _reset_for_tests() -> None:
    """Test helper: clear the registry."""
    _SECTIONS.clear()
