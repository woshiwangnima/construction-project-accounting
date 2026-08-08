"""ScrollableFrame: Canvas + Scrollbar wrapper with auto-hide support."""

import tkinter as tk
from tkinter import ttk

from ..theme import APP_BG, BORDER, TABLE_HEADER_BG, TEXT_SECONDARY, TEXT_TERTIARY

_SCROLLBAR_STYLE = "CPA.Vertical.TScrollbar"


def _scrollbar_style_name() -> str:
    style = ttk.Style()
    style.configure(
        _SCROLLBAR_STYLE,
        troughcolor=TABLE_HEADER_BG,
        bordercolor=BORDER,
        background=TEXT_TERTIARY,
        lightcolor=TEXT_TERTIARY,
        darkcolor=TEXT_TERTIARY,
        arrowcolor=TEXT_SECONDARY,
    )
    style.map(
        _SCROLLBAR_STYLE,
        background=[("active", TEXT_SECONDARY)],
    )
    return _SCROLLBAR_STYLE


class ScrollableFrame(tk.Frame):
    """A scrollable container with an always-visible or auto-hiding scrollbar.

    Parameters:
        parent: tkinter parent widget
        auto_hide_ms: None=always visible, >0=hide after N ms of no scroll
        scroll_step: units per scroll tick (default 3)
        bg: background color
    """

    def __init__(
        self,
        parent,
        auto_hide_ms: int | None = None,
        scroll_step: int = 3,
        bg: str = APP_BG,
        **kwargs,
    ):
        kwargs.setdefault("bg", bg)
        super().__init__(parent, **kwargs)
        self.pack_propagate(False)

        self._auto_hide_ms = auto_hide_ms
        self._scroll_step = scroll_step
        self._hide_after_id = None
        self._layout_after_id = None
        self._focus_after_id = None
        self._scrollbar_visible = False
        self._canvas_window_width = None
        self._scrollregion = None
        self._destroyed = False

        self.canvas = tk.Canvas(self, borderwidth=0, highlightthickness=0, bg=bg)
        self.scrollbar = ttk.Scrollbar(
            self, orient=tk.VERTICAL, command=self.canvas.yview,
            style=_scrollbar_style_name(),
        )
        self.canvas.configure(yscrollcommand=self._on_scrollbar_set)
        self.inner = tk.Frame(self.canvas, bg=bg)
        self.inner.bind("<Configure>", self._on_inner_configure)
        self.canvas_win = self.canvas.create_window((0, 0), window=self.inner, anchor="nw")
        self.canvas.bind("<Configure>", self._on_canvas_configure)

        # scrollbar 必须先 pack 以保留右侧空间；canvas expand=True 填充剩余区域
        if auto_hide_ms is not None:
            # 自动隐藏模式：初始不 pack，滚动时再显示
            self._scrollbar_visible = False
        else:
            self.scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
            self._scrollbar_visible = True
        self.canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        self._bind_events()

    def _bind_events(self):
        self.canvas.bind("<MouseWheel>", self._on_mousewheel)
        self.canvas.bind("<Button-4>", self._on_scroll_up)
        self.canvas.bind("<Button-5>", self._on_scroll_down)
        self.inner.bind("<MouseWheel>", self._on_mousewheel)
        self.inner.bind("<Button-4>", self._on_scroll_up)
        self.inner.bind("<Button-5>", self._on_scroll_down)
        self.canvas.bind("<Up>", self._on_scroll_up)
        self.canvas.bind("<Down>", self._on_scroll_down)
        self.inner.bind("<Up>", self._on_scroll_up)
        self.inner.bind("<Down>", self._on_scroll_down)
        self.canvas.bind("<Button-1>", self._on_click_focus, add="+")
        self.inner.bind("<Button-1>", self._on_click_focus, add="+")
        self._focus_after_id = self.after_idle(self._focus_canvas)

    def _focus_canvas(self):
        self._focus_after_id = None
        try:
            if self.canvas.winfo_exists():
                self.canvas.focus_set()
        except tk.TclError:
            pass

    def _on_scroll_up(self, _event=None):
        self._scroll(-1)

    def _on_scroll_down(self, _event=None):
        self._scroll(1)

    def _on_inner_configure(self, _event=None):
        self._schedule_layout_update()

    def _on_canvas_configure(self, _event=None):
        self._schedule_layout_update()

    def _schedule_layout_update(self):
        if self._destroyed:
            return
        if self._layout_after_id is None:
            self._layout_after_id = self.after_idle(self._sync_layout)

    def _sync_layout(self):
        self._layout_after_id = None
        if self._destroyed:
            return
        try:
            if not self.canvas.winfo_exists() or not self.inner.winfo_exists():
                return
            width = max(int(self.canvas.winfo_width()), 60)
            if width != self._canvas_window_width:
                self.canvas.itemconfigure(self.canvas_win, width=width)
                self._canvas_window_width = width
            bbox = self.canvas.bbox("all")
            if bbox != self._scrollregion:
                self.canvas.configure(scrollregion=bbox)
                self._scrollregion = bbox
        except tk.TclError:
            pass

    def _on_click_focus(self, event):
        if not isinstance(event.widget, (tk.Entry, ttk.Entry)):
            self.canvas.focus_set()

    def _on_mousewheel(self, event):
        delta = -1 * (event.delta / 120) if event.delta else 0
        if delta:
            self._scroll(int(delta))

    def _scroll(self, units):
        try:
            if self._destroyed or not self.canvas.winfo_exists():
                return
            sr = self.canvas.cget("scrollregion")
            _, y1, _, y2 = map(float, sr.split())
        except (ValueError, tk.TclError):
            return
        if y2 - y1 <= self.canvas.winfo_height():
            return
        self.canvas.yview_scroll(units * self._scroll_step, "units")
        self._show_scrollbar()

    def _show_scrollbar(self):
        if self._auto_hide_ms is not None:
            if not self._scrollbar_visible:
                self.scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
                self._scrollbar_visible = True
            self._reset_hide_timer()

    def _reset_hide_timer(self):
        if self._hide_after_id is not None:
            try:
                self.after_cancel(self._hide_after_id)
            except (tk.TclError, RuntimeError):
                pass
            self._hide_after_id = None
        if self._auto_hide_ms is not None:
            self._hide_after_id = self.after(self._auto_hide_ms, self._hide_scrollbar)

    def _hide_scrollbar(self):
        self._hide_after_id = None
        if self._scrollbar_visible:
            self.scrollbar.pack_forget()
            self._scrollbar_visible = False

    def _on_scrollbar_set(self, first, last):
        self.scrollbar.set(first, last)
        if self._auto_hide_ms is not None:
            sr = self.canvas.cget("scrollregion")
            try:
                _, y1, _, y2 = map(float, sr.split())
            except (ValueError, tk.TclError):
                return
            if y2 - y1 <= self.canvas.winfo_height():
                if self._scrollbar_visible:
                    self.scrollbar.pack_forget()
                    self._scrollbar_visible = False

    def update_scrollregion(self):
        if self._layout_after_id is not None:
            try:
                self.after_cancel(self._layout_after_id)
            except (tk.TclError, RuntimeError):
                pass
            self._layout_after_id = None
        self._sync_layout()

    def scroll_to_top(self):
        self.canvas.yview_moveto(0)

    def bind_all_children(self, callback):
        """Bind events to inner frame. Tkinter event propagation covers all children."""
        self.inner.bind("<MouseWheel>", callback, add="+")

    def destroy(self):
        """Cancel deferred layout, focus, and auto-hide callbacks before teardown."""
        self._destroyed = True
        for attr_name in ("_hide_after_id", "_layout_after_id", "_focus_after_id"):
            timer_id = getattr(self, attr_name, None)
            if timer_id is None:
                continue
            try:
                self.after_cancel(timer_id)
            except (tk.TclError, RuntimeError):
                pass
            setattr(self, attr_name, None)
        super().destroy()
