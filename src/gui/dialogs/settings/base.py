"""Settings panel base class and registry.

Use the @register_section decorator to register a panel.
SettingsDialog auto-discovers all registered sections via get_sections().
"""

import tkinter as tk
from typing import ClassVar

from ...theme import APP_BG
from ....logger import logger


_SECTIONS: list[type["BaseSettingsPanel"]] = []


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
        flush_pending()  is auto-called by SettingsDialog on section switch / close
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

    def _schedule_save(self) -> None:
        """Schedule a debounced auto-save (300ms). Safe to call from var traces."""
        if self._loading:
            return
        if self._save_after_id is not None:
            try:
                self.after_cancel(self._save_after_id)
            except Exception:
                pass
        self._pending_save = True
        self._save_after_id = self.after(300, self._auto_save)

    def _auto_save(self) -> None:
        self._save_after_id = None
        self._pending_save = False
        try:
            self._save()
        except Exception as e:
            logger.warning("设置自动保存失败 (%s): %s", self.section_id, e)

    def flush_pending(self) -> None:
        """Force-flush any pending debounced save. Called on panel switch / dialog close."""
        if not self._pending_save:
            return
        if self._save_after_id is not None:
            try:
                self.after_cancel(self._save_after_id)
            except Exception:
                pass
            self._save_after_id = None
        self._pending_save = False
        try:
            self._save()
        except Exception as e:
            logger.warning("设置保存失败 (%s): %s", self.section_id, e)


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
