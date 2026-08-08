"""表头组件：支持动态换行动态行高 + 列头点击回调"""

import tkinter as tk

from ..theme import TABLE_HEADER_BG, TABLE_HEADER_FG, TEXT_SECONDARY, TEXT_TERTIARY, ACCENT
from ..font_manager import font_manager
from ...logger import logger


class TableHeader(tk.Frame):
    HANDLE_WIDTH = 4
    HANDLE_BG = TEXT_TERTIARY
    HANDLE_HOVER_BG = TEXT_SECONDARY

    def __init__(self, parent, columns, pixels, header_click_map=None,
                 on_drag_start=None, display_names=None):
        super().__init__(parent, bg=TABLE_HEADER_BG)
        self._columns = columns
        self._pixels = pixels
        self._header_click_map = header_click_map or {}
        self._on_drag_start = on_drag_start
        self._display_names = display_names or {}
        self._cells: dict[str, tk.Frame] = {}
        self._labels: dict[str, tk.Label] = {}
        self._build()
        self._bind_clicks()

    def _build(self):
        for idx, col in enumerate(self._columns):
            self.grid_columnconfigure(idx, minsize=self._pixels.get(col, 80))
            cell = tk.Frame(self, bg=TABLE_HEADER_BG)
            lbl = tk.Label(cell, text=self._display_names.get(col, col), font=font_manager.get("body_bold"), bg=TABLE_HEADER_BG,
                           fg=TABLE_HEADER_FG, anchor="w", padx=8, wraplength=0)
            lbl.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
            if idx < len(self._columns) - 1:
                handle = tk.Frame(cell, bg=self.HANDLE_BG,
                                  width=self.HANDLE_WIDTH, cursor="sb_h_double_arrow")
                handle.pack(side=tk.RIGHT, fill=tk.Y)
                if self._on_drag_start:
                    handle.bind("<ButtonPress-1>",
                                lambda e, i=idx: self._on_drag_start(i, e))
                    handle.bind("<Enter>", lambda e, h=handle: h.config(bg=self.HANDLE_HOVER_BG))
                    handle.bind("<Leave>", lambda e, h=handle: h.config(bg=self.HANDLE_BG))
            cell.grid(row=0, column=idx, sticky="nsew")
            self._cells[col] = cell
            self._labels[col] = lbl

    def _bind_clicks(self):
        _uh = font_manager.get("body_bold").copy()
        _uh.configure(underline=True)
        underline_font = _uh
        for col, callback in self._header_click_map.items():
            lbl = self._labels.get(col)
            if lbl:
                lbl.config(cursor="hand2", fg=ACCENT,
                           font=underline_font)
                lbl.bind("<Button-1>", lambda e, c=col, cb=callback: cb(c))
                logger.debug("TableHeader: bound click for col=%s", col)

    def set_sort_indicator(self, col: str, direction: str | None):
        """设置排序列的箭头指示。direction: 'asc' | 'desc' | None 清除。"""
        lbl = self._labels.get(col)
        if not lbl:
            return
        text = self._display_names.get(col, col)
        if direction == "asc":
            text = "▲ " + text
        elif direction == "desc":
            text = "▼ " + text
        lbl.config(text=text)

    def refresh_widths(self, pixels: dict[str, int]):
        self._pixels = pixels
        for idx, col in enumerate(self._columns):
            self.grid_columnconfigure(idx, minsize=pixels.get(col, 80))
            lbl = self._labels.get(col)
            if lbl:
                lbl.config(wraplength=max(pixels.get(col, 80) - 16, 8))
