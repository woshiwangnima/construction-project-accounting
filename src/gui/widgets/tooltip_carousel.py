"""TooltipCarousel: rotating tooltip with horizontal scroll for long text."""

import tkinter as tk

from ..theme import APP_BG, TEXT_SECONDARY


class TooltipCarousel(tk.Frame):
    """Cycles through messages, auto-scrolling horizontally if text overflows.

    Parameters:
        parent: tkinter parent widget
        messages: list of strings to display
        dwell_per_char_ms: ms per character for timing (default 80)
        font_size: font size for label (default 13)
        fg: text color
        bg: background color
    """

    def __init__(
        self,
        parent,
        messages,
        prefix="",
        dwell_per_char_ms=80,
        font_size=13,
        fg=TEXT_SECONDARY,
        bg=APP_BG,
        anchor="w",
        **kwargs,
    ):
        super().__init__(parent, bg=bg, **kwargs)
        self._messages = list(messages)
        self._prefix = prefix
        self._dwell_per_char_ms = dwell_per_char_ms
        self._font_size = font_size
        self._fg = fg
        self._bg = bg
        self._anchor = anchor
        self._index = 0
        self._anim_after_id = None
        self._offset = 0

        self._label = tk.Label(
            self, text="", font=("Microsoft YaHei UI", font_size),
            bg=bg, fg=fg, anchor=anchor,
        )
        self._label.pack(fill=tk.X, expand=True)

        if self._messages:
            self.after(100, self._show_current)

    def _show_current(self):
        if not self._messages or self._index >= len(self._messages):
            self._index = 0
            if not self._messages:
                return
        msg = self._prefix + self._messages[self._index]
        self._label.config(text=msg)
        self.update_idletasks()

        text_width = self._label.winfo_reqwidth()
        container_width = self.winfo_width()

        if text_width <= container_width:
            self._label.config(anchor="center")
            dwell = max(1000, len(msg) * self._dwell_per_char_ms)
            self._anim_after_id = self.after(dwell, self._next_message)
        else:
            self._label.config(anchor="w")
            self._offset = 0
            self._scroll_forward()

    def _scroll_forward(self):
        msg = self._prefix + self._messages[self._index]
        self._label.config(text=msg + "    ")
        self.update_idletasks()
        container_w = self.winfo_width()
        text_w = self._label.winfo_reqwidth()
        total_distance = text_w - container_w

        self._offset = 0
        self._do_scroll(total_distance, 1, self._scroll_backward)

    def _scroll_backward(self):
        container_w = self.winfo_width()
        total_distance = self._label.winfo_reqwidth() - container_w
        self._offset = total_distance
        self._do_scroll(total_distance, -1, self._next_message)

    def _do_scroll(self, distance, direction, on_done):
        if distance <= 0:
            self.after(50, on_done)
            return

        step = 2

        def _tick():
            self._offset += direction * step
            if direction > 0:
                if self._offset >= distance:
                    self._offset = distance
                    self.after(self._dwell_per_char_ms * 5, on_done)
                    return
            else:
                if self._offset <= 0:
                    self._offset = 0
                    self.after(50, on_done)
                    return

            self._label.place(x=-self._offset, y=0)
            self._anim_after_id = self.after(self._dwell_per_char_ms, _tick)

        _tick()

    def _next_message(self):
        self._label.place_forget()
        self._label.pack(fill=tk.X, expand=True)
        self._index += 1
        if self._index >= len(self._messages):
            self._index = 0
        self._show_current()

    def set_messages(self, messages):
        self._messages = list(messages)
        self._index = 0
        if self._anim_after_id:
            try:
                self.after_cancel(self._anim_after_id)
            except tk.TclError:
                pass
        self._show_current()

    def destroy(self):
        if self._anim_after_id:
            try:
                self.after_cancel(self._anim_after_id)
            except tk.TclError:
                pass
        super().destroy()
