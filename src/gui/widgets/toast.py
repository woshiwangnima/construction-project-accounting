"""可排队、可动画的 Toast 通知组件。"""

from __future__ import annotations

import tkinter as tk
from dataclasses import dataclass
from ...config_loader import load_app


@dataclass
class ToastSettings:
    """Toast 动画时序配置，所有字段均可在设置面板调整。"""
    duration_ms: int = 5000
    fade_in_ms: int = 300
    float_ms: int = 700
    queue_interval_ms: int = 1000

    def to_dict(self) -> dict:
        return {
            "duration_ms": self.duration_ms,
            "fade_in_ms": self.fade_in_ms,
            "float_ms": self.float_ms,
            "queue_interval_ms": self.queue_interval_ms,
        }

    @classmethod
    def from_dict(cls, d: dict) -> ToastSettings:
        return cls(
            duration_ms=d.get("duration_ms", 5000),
            fade_in_ms=d.get("fade_in_ms", 300),
            float_ms=d.get("float_ms", 700),
            queue_interval_ms=d.get("queue_interval_ms", 1000),
        )

    @classmethod
    def load(cls) -> ToastSettings:
        cfg = load_app().get("toast_settings", {})
        return cls.from_dict(cfg)


class ToastNotification:
    """全局 Toast 通知管理器（队列单例）。"""

    _STEP_MS = 16

    def __init__(self, root: tk.Tk):
        self._root = root
        self._queue: list[tuple[str, int | None]] = []
        self._active = False
        self._window: tk.Toplevel | None = None
        self._after_id: str | None = None

    def show(self, message: str, duration: int | None = None) -> None:
        self._queue.append((message, duration))
        if not self._active:
            self._next()
        else:
            self._shorten_current()

    def cancel_all(self) -> None:
        self._queue.clear()
        self._destroy_current()

    # ── 队列管理 ──

    def _next(self) -> None:
        if not self._queue:
            self._active = False
            return
        self._active = True
        msg, override_ms = self._queue.pop(0)
        s = ToastSettings.load()
        has_more = bool(self._queue)
        self._show_animated(msg, s, override_ms, has_more)

    def _shorten_current(self) -> None:
        if self._window is None:
            return
        s = ToastSettings.load()
        new_total = s.fade_in_ms + s.queue_interval_ms + s.float_ms
        if self._anim_elapsed >= new_total:
            self._destroy_current()
            self._on_anim_end()
            return
        self._anim_total_ms = new_total
        self._anim_hold = max(0, new_total - s.fade_in_ms - s.float_ms)

    # ── 动画 ──

    def _show_animated(self, msg: str, s: ToastSettings,
                       override_ms: int | None, has_more: bool) -> None:
        self._destroy_current()
        total_ms = override_ms if override_ms is not None else s.duration_ms
        if has_more:
            total_ms = min(total_ms, s.fade_in_ms + s.queue_interval_ms + s.float_ms)
        fade_in_ms = s.fade_in_ms
        float_ms = s.float_ms
        hold_ms = max(0, total_ms - fade_in_ms - float_ms)
        tw, base_y = self._build_window(msg)
        self._window = tw
        self._anim_fade_in = fade_in_ms
        self._anim_float = float_ms
        self._anim_hold = hold_ms
        self._anim_total_ms = total_ms
        self._anim_elapsed = 0
        self._anim_start_y = base_y
        self._anim_alpha = 0.0
        self._tick()

    def _tick(self) -> None:
        tw = self._window
        if tw is None:
            self._on_anim_end()
            return
        self._anim_elapsed += self._STEP_MS
        fi = self._anim_fade_in
        hold = self._anim_hold
        fl = self._anim_float
        if self._anim_elapsed < fi:
            self._anim_alpha = self._anim_elapsed / fi
        elif self._anim_elapsed < fi + hold:
            self._anim_alpha = 1.0
        elif self._anim_elapsed < self._anim_total_ms:
            progress = (self._anim_elapsed - fi - hold) / fl
            self._anim_alpha = 1.0 - progress
            dy = int(80 * progress)
            try:
                tw.geometry(f"+{tw.winfo_x()}+{self._anim_start_y - dy}")
            except tk.TclError:
                self._destroy_current()
                self._on_anim_end()
                return
        else:
            self._destroy_current()
            self._on_anim_end()
            return
        try:
            tw.wm_attributes("-alpha", max(0.0, min(1.0, self._anim_alpha)))
        except tk.TclError:
            self._destroy_current()
            self._on_anim_end()
            return
        self._after_id = tw.after(self._STEP_MS, self._tick)

    # ── 窗口创建 ──

    def _build_window(self, msg: str) -> tuple:
        tw = tk.Toplevel(self._root)
        tw.wm_overrideredirect(True)
        tw.wm_attributes("-topmost", True)
        tw.configure(bg="#2d3748")
        lbl = tk.Label(tw, text=msg, bg="#2d3748", fg="white",
                       font=("Microsoft YaHei UI", 12), padx=20, pady=10)
        lbl.pack()
        self._root.update_idletasks()
        sx = self._root.winfo_screenwidth()
        sy = self._root.winfo_screenheight()
        tw.update_idletasks()
        w = tw.winfo_reqwidth()
        h = tw.winfo_reqheight()
        base_x = (sx - w) // 2
        base_y = sy - h - 120
        tw.geometry(f"+{base_x}+{base_y}")
        return tw, base_y

    def _destroy_current(self) -> None:
        if self._after_id is not None and self._window:
            try:
                self._window.after_cancel(self._after_id)
            except tk.TclError:
                pass
        self._after_id = None
        if self._window:
            try:
                self._window.destroy()
            except tk.TclError:
                pass
        self._window = None

    def _on_anim_end(self) -> None:
        self._active = False
        if self._queue:
            self._next()
