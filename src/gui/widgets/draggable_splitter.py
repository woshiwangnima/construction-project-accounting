"""DraggableSplitter: resizable panel separator."""

import tkinter as tk

from ..theme import SIDEBAR_ITEM_BORDER
from ...logger import logger


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
        name: optional name for debug logging
        ref_widget: optional widget whose width is used for ratio calculation
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
        name="",
        ref_widget=None,
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
        self._name = name or "splitter"
        self._ref_widget = ref_widget

        self.bind("<Button-1>", self._on_press)
        self.bind("<B1-Motion>", self._on_drag)
        self.bind("<ButtonRelease-1>", self._on_release)

    def _ref_w(self):
        if self._ref_widget:
            try:
                return self._ref_widget.winfo_width()
            except tk.TclError:
                pass
        return 0

    def _on_press(self, event):
        self._dragging = True
        self._start_x = event.x_root
        self._start_width = self._target.winfo_width()
        parent_w = self.master.winfo_width() if self.master else 0
        logger.debug("[%s] press: start_width=%s parent_w=%s ref_w=%s",
                     self._name, self._start_width, parent_w, self._ref_w())

    def _on_drag(self, event):
        if not self._dragging:
            return
        dx = event.x_root - self._start_x
        new_width = max(self._min_width, min(self._max_width, self._start_width + dx))
        self._target.configure(width=new_width)
        # 强制 pack 几何管理器立即重算，否则 winfo_width() 返回旧值，
        # 导致拖拽时视觉宽度滞后于鼠标位置。
        self._target.update_idletasks()

    def _on_release(self, event):
        if not self._dragging:
            return
        self._dragging = False
        final = self._target.winfo_width()
        parent_w = self.master.winfo_width() if self.master else 0
        ref_w = self._ref_w()
        ratio = final / max(ref_w, 1) if ref_w else final / max(parent_w, 1)
        logger.debug("[%s] release: final=%s parent_w=%s ref_w=%s ratio=%.6f",
                     self._name, final, parent_w, ref_w, ratio)
        if self._on_resize:
            self._on_resize(final)
