"""ScrollableFrame: Canvas + Scrollbar wrapper with auto-hide support."""

import tkinter as tk
from tkinter import ttk

from ..theme import APP_BG


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
        self._scrollbar_visible = False

        self.canvas = tk.Canvas(self, borderwidth=0, highlightthickness=0, bg=bg)
        self.scrollbar = ttk.Scrollbar(self, orient=tk.VERTICAL, command=self.canvas.yview)
        self.canvas.configure(yscrollcommand=self._on_scrollbar_set)
        self.inner = tk.Frame(self.canvas, bg=bg)
        self.inner.bind(
            "<Configure>",
            lambda e: self.canvas.configure(scrollregion=self.canvas.bbox("all")),
        )
        self.canvas_win = self.canvas.create_window((0, 0), window=self.inner, anchor="nw")
        self.canvas.bind(
            "<Configure>",
            lambda e: self.canvas.itemconfig(self.canvas_win, width=max(e.width, 60)),
        )

        self.canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        if auto_hide_ms is not None:
            self.scrollbar.pack_forget()
        else:
            self.scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
            self._scrollbar_visible = True

        self._bind_events()

    def _bind_events(self):
        self.canvas.bind("<MouseWheel>", self._on_mousewheel)
        self.canvas.bind("<Button-4>", lambda e: self._scroll(-1))
        self.canvas.bind("<Button-5>", lambda e: self._scroll(1))
        self.inner.bind("<MouseWheel>", self._on_mousewheel)
        self.inner.bind("<Button-4>", lambda e: self._scroll(-1))
        self.inner.bind("<Button-5>", lambda e: self._scroll(1))
        self.canvas.bind("<Up>", lambda e: self._scroll(-1))
        self.canvas.bind("<Down>", lambda e: self._scroll(1))
        self.inner.bind("<Up>", lambda e: self._scroll(-1))
        self.inner.bind("<Down>", lambda e: self._scroll(1))
        self.canvas.bind("<Button-1>", self._on_click_focus, add="+")
        self.inner.bind("<Button-1>", self._on_click_focus, add="+")
        self.after_idle(self.canvas.focus_set)

    def _on_click_focus(self, event):
        if not isinstance(event.widget, (tk.Entry, ttk.Entry)):
            self.canvas.focus_set()

    def _on_mousewheel(self, event):
        delta = -1 * (event.delta / 120) if event.delta else 0
        if delta:
            self._scroll(int(delta))

    def _scroll(self, units):
        sr = self.canvas.cget("scrollregion")
        try:
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
        if self._hide_after_id:
            try:
                self.after_cancel(self._hide_after_id)
            except tk.TclError:
                pass
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
        self.canvas.configure(scrollregion=self.canvas.bbox("all"))

    def scroll_to_top(self):
        self.canvas.yview_moveto(0)

    def bind_all_children(self, callback):
        """Bind events to inner frame. Tkinter event propagation covers all children."""
        self.inner.bind("<MouseWheel>", callback, add="+")
