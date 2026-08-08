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
        self._dwell_per_char_ms = max(1, int(dwell_per_char_ms))
        self._font_size = font_size
        self._fg = fg
        self._bg = bg
        self._index = 0
        self._anim_after_id = None
        self._init_after_id = None
        self._animation_generation = 0
        self._offset = 0
        self._last_configure_size = None
        self._destroyed = False

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
            generation = self._animation_generation
            self._init_after_id = self.after(
                100, lambda token=generation: self._show_current(token)
            )

    def _show_current(self, generation: int | None = None):
        if generation is not None and generation != self._animation_generation:
            return
        self._init_after_id = None
        if self._destroyed:
            return
        if not self._messages or self._index >= len(self._messages):
            self._index = 0
            if not self._messages:
                self._canvas.itemconfig(self._text_id, text="")
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
            dwell = max(1000, len(msg) * self._dwell_per_char_ms)
            token = self._animation_generation
            self._anim_after_id = self.after(
                dwell, lambda token=token: self._next_message(token)
            )
        else:
            self._offset = 0
            self._canvas.coords(self._text_id, 0, cy)
            self._scroll_forward(text_width - container_width,
                                 self._animation_generation)

    def _scroll_forward(self, total_distance, generation=None):
        if generation is None:
            generation = self._animation_generation
        cy = self._canvas.winfo_height() // 2

        def tick():
            if self._destroyed or generation != self._animation_generation:
                return
            self._offset += _SCROLL_STEP
            if self._offset >= total_distance:
                self._offset = total_distance
                self._canvas.coords(self._text_id, -self._offset, cy)
                pause = self._dwell_per_char_ms * _SCROLL_PAUSE_MULTIPLIER
                self._anim_after_id = self.after(
                    pause,
                    lambda token=generation: self._scroll_backward(
                        total_distance, token
                    ),
                )
                return
            self._canvas.coords(self._text_id, -self._offset, cy)
            self._anim_after_id = self.after(self._dwell_per_char_ms, tick)
        tick()

    def _scroll_backward(self, total_distance, generation=None):
        if generation is None:
            generation = self._animation_generation
        cy = self._canvas.winfo_height() // 2

        def tick():
            if self._destroyed or generation != self._animation_generation:
                return
            self._offset -= _SCROLL_STEP
            if self._offset <= 0:
                self._offset = 0
                self._canvas.coords(self._text_id, 0, cy)
                self._anim_after_id = self.after(
                    _NEXT_MSG_DELAY_MS,
                    lambda token=generation: self._next_message(token),
                )
                return
            self._canvas.coords(self._text_id, -self._offset, cy)
            self._anim_after_id = self.after(self._dwell_per_char_ms, tick)
        tick()

    def _next_message(self, generation=None):
        if generation is not None and generation != self._animation_generation:
            return
        self._anim_after_id = None
        if self._destroyed:
            return
        self._index += 1
        if self._index >= len(self._messages):
            self._index = 0
        self._show_current(generation)

    def _cancel_anim(self):
        self._animation_generation += 1
        if self._init_after_id is not None:
            try:
                self.after_cancel(self._init_after_id)
            except (tk.TclError, RuntimeError):
                pass
            self._init_after_id = None
        if self._anim_after_id is not None:
            try:
                self.after_cancel(self._anim_after_id)
            except (tk.TclError, RuntimeError):
                pass
            self._anim_after_id = None
        if self._configure_after_id is not None:
            try:
                self.after_cancel(self._configure_after_id)
            except (tk.TclError, RuntimeError):
                pass
            self._configure_after_id = None

    def set_messages(self, messages):
        if self._destroyed:
            return
        self._messages = list(messages)
        self._index = 0
        self._offset = 0
        self._cancel_anim()
        if not self._messages:
            self._canvas.itemconfig(self._text_id, text="")
            return
        generation = self._animation_generation
        self._init_after_id = self.after(
            100, lambda token=generation: self._show_current(token)
        )

    def _on_configure(self, event):
        """Debounced re-center on resize."""
        if self._destroyed or not self._messages:
            return
        size = (getattr(event, "width", None), getattr(event, "height", None))
        if size == self._last_configure_size:
            return
        self._last_configure_size = size
        if self._configure_after_id is not None:
            try:
                self.after_cancel(self._configure_after_id)
            except (tk.TclError, RuntimeError):
                pass
        generation = self._animation_generation
        self._configure_after_id = self.after(
            50, lambda token=generation: self._recenter(token)
        )

    def _recenter(self, generation=None):
        """Re-position current message text after resize."""
        if generation is not None and generation != self._animation_generation:
            return
        self._configure_after_id = None
        if self._destroyed or not self._messages:
            return
        msg = self._prefix + self._messages[self._index]
        self._canvas.itemconfig(self._text_id, text=msg)
        bbox = self._canvas.bbox(self._text_id)
        text_width = bbox[2] - bbox[0] if bbox else 0
        container_width = self._canvas.winfo_width()
        cy = self._canvas.winfo_height() // 2
        if text_width <= container_width:
            self._offset = 0
            x = max(0, (container_width - text_width) // 2)
            self._canvas.coords(self._text_id, x, cy)
        else:
            # Long text: keep current scroll offset
            self._offset = min(max(self._offset, 0), text_width - container_width)
            self._canvas.coords(self._text_id, -self._offset, cy)

    def destroy(self):
        self._destroyed = True
        self._cancel_anim()
        self._messages.clear()
        super().destroy()
