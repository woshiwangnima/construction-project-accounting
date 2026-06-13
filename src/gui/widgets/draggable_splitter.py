"""DraggableSplitter: resizable panel separator."""

import tkinter as tk

from ..theme import SIDEBAR_ITEM_BORDER


class DraggableSplitter(tk.Frame):
    """A draggable vertical splitter bar for resizing adjacent panels.

    Parameters:
        parent: tkinter parent widget
        target: the widget whose width to adjust
        min_width: minimum target width (default 200)
        max_width: maximum target width (default 500)
        on_resize: called with (new_width) on mouse release
        default_width: initial target width (default 320)
        bg: splitter color
    """

    def __init__(
        self,
        parent,
        target,
        min_width=200,
        max_width=500,
        on_resize=None,
        default_width=320,
        bg=None,
    ):
        if bg is None:
            bg = SIDEBAR_ITEM_BORDER
        super().__init__(parent, bg=bg, width=6, cursor="sb_h_double_arrow")
        self.pack_propagate(False)

        self._target = target
        self._min_width = min_width
        self._max_width = max_width
        self._on_resize = on_resize
        self._dragging = False
        self._start_x = 0
        self._start_width = default_width

        self.bind("<Button-1>", self._on_press)
        self.bind("<B1-Motion>", self._on_drag)
        self.bind("<ButtonRelease-1>", self._on_release)

    def _on_press(self, event):
        self._dragging = True
        self._start_x = event.x_root
        self._start_width = self._target.winfo_width()

    def _on_drag(self, event):
        if not self._dragging:
            return
        dx = event.x_root - self._start_x
        new_width = max(self._min_width, min(self._max_width, self._start_width + dx))
        self._target.configure(width=new_width)

    def _on_release(self, event):
        if not self._dragging:
            return
        self._dragging = False
        if self._on_resize:
            self._on_resize(self._target.winfo_width())
