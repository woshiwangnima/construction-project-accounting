"""TooltipCarousel: rotating tooltip with horizontal scroll for long text."""

import tkinter as tk

from ..theme import APP_BG, TEXT_SECONDARY

_SCROLL_STEP = 2
_SCROLL_PAUSE_MULTIPLIER = 5
_NEXT_MSG_DELAY_MS = 50
_LINE_HEIGHT_PADDING = 6


class TooltipCarousel(tk.Frame):
    """Cycles through messages, auto-scrolling horizontally if text overflows.

    Uses a Canvas to avoid geometry-manager toggling (pack/place conflict).
    """

    def __init__(self, parent, messages, prefix="", dwell_per_char_ms=80,
                 font_size=13, fg=TEXT_SECONDARY, bg=APP_BG, anchor="w", **kwargs):
        super().__init__(parent, bg=bg, **kwargs)
        self._messages = list(messages)
        self._prefix = prefix
        self._dwell_per_char_ms = dwell_per_char_ms
        self._font_size = font_size
        self._fg = fg
        self._bg = bg
        self._index = 0
        self._anim_after_id = None
        self._init_after_id = None
        self._offset = 0

        font_obj = ("Microsoft YaHei UI", font_size)
        line_height = font_size + _LINE_HEIGHT_PADDING
        self.configure(height=line_height)
        self.pack_propagate(False)

        self._canvas = tk.Canvas(self, bg=bg, highlightthickness=0, bd=0, height=line_height)
        self._canvas.pack(fill=tk.X)
        self._configure_after_id = None
        self._canvas.bind("<Configure>", self._on_configure)

        # Always use "w" anchor — coordinate math handles centering
        self._text_id = self._canvas.create_text(
            0, line_height // 2, text="", anchor="w", fill=fg,
            font=font_obj, tags="msg",
        )

        if self._messages:
            self._init_after_id = self.after(100, self._show_current)

    def _show_current(self):
        if not self._messages or self._index >= len(self._messages):
            self._index = 0
            if not self._messages:
                return
        msg = self._prefix + self._messages[self._index]
        self._canvas.itemconfig(self._text_id, text=msg)
        self.update_idletasks()

        bbox = self._canvas.bbox(self._text_id)
        text_width = bbox[2] - bbox[0] if bbox else 0
        container_width = self._canvas.winfo_width()
        cy = self._canvas.winfo_height() // 2

        if text_width <= container_width:
            x = max(0, (container_width - text_width) // 2)
            self._canvas.coords(self._text_id, x, cy)
            dwell = max(1000, len(msg) * self._dwell_per_char_ms)
            self._anim_after_id = self.after(dwell, self._next_message)
        else:
            self._offset = 0
            self._canvas.coords(self._text_id, 0, cy)
            self._scroll_forward(text_width - container_width)

    def _scroll_forward(self, total_distance):
        cy = self._canvas.winfo_height() // 2

        def tick():
            self._offset += _SCROLL_STEP
            if self._offset >= total_distance:
                self._offset = total_distance
                self._canvas.coords(self._text_id, -self._offset, cy)
                pause = self._dwell_per_char_ms * _SCROLL_PAUSE_MULTIPLIER
                self._anim_after_id = self.after(pause, lambda: self._scroll_backward(total_distance))
                return
            self._canvas.coords(self._text_id, -self._offset, cy)
            self._anim_after_id = self.after(self._dwell_per_char_ms, tick)
        tick()

    def _scroll_backward(self, total_distance):
        cy = self._canvas.winfo_height() // 2

        def tick():
            self._offset -= _SCROLL_STEP
            if self._offset <= 0:
                self._offset = 0
                self._canvas.coords(self._text_id, 0, cy)
                self._anim_after_id = self.after(_NEXT_MSG_DELAY_MS, self._next_message)
                return
            self._canvas.coords(self._text_id, -self._offset, cy)
            self._anim_after_id = self.after(self._dwell_per_char_ms, tick)
        tick()

    def _next_message(self):
        self._index += 1
        if self._index >= len(self._messages):
            self._index = 0
        self._show_current()

    def _cancel_anim(self):
        if self._init_after_id:
            try:
                self.after_cancel(self._init_after_id)
            except tk.TclError:
                pass
            self._init_after_id = None
        if self._anim_after_id:
            try:
                self.after_cancel(self._anim_after_id)
            except tk.TclError:
                pass
            self._anim_after_id = None
        if self._configure_after_id:
            try:
                self.after_cancel(self._configure_after_id)
            except tk.TclError:
                pass
            self._configure_after_id = None

    def set_messages(self, messages):
        self._messages = list(messages)
        self._index = 0
        self._cancel_anim()
        self._init_after_id = self.after(100, self._show_current)

    def _on_configure(self, event):
        """Debounced re-center on resize."""
        if self._configure_after_id:
            try:
                self.after_cancel(self._configure_after_id)
            except tk.TclError:
                pass
        self._configure_after_id = self.after(50, self._recenter)

    def _recenter(self):
        """Re-position current message text after resize."""
        self._configure_after_id = None
        if not self._messages:
            return
        msg = self._prefix + self._messages[self._index]
        self._canvas.itemconfig(self._text_id, text=msg)
        bbox = self._canvas.bbox(self._text_id)
        text_width = bbox[2] - bbox[0] if bbox else 0
        container_width = self._canvas.winfo_width()
        cy = self._canvas.winfo_height() // 2
        if text_width <= container_width:
            x = max(0, (container_width - text_width) // 2)
            self._canvas.coords(self._text_id, x, cy)
        else:
            # Long text: keep current scroll offset
            self._canvas.coords(self._text_id, -self._offset, cy)

    def destroy(self):
        self._cancel_anim()
        super().destroy()
