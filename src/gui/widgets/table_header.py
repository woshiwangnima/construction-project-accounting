"""表头组件：支持动态换行动态行高 + 列头点击回调"""

import tkinter as tk

from ..theme import FONT_BODY_BOLD, TEXT_PRIMARY


class TableHeader(tk.Frame):
    HANDLE_WIDTH = 4
    HANDLE_BG = "#a0aec0"
    HANDLE_HOVER_BG = "#4a5568"

    def __init__(self, parent, columns, pixels, header_click_map=None,
                 on_drag_start=None):
        super().__init__(parent, bg="#e8e8e8")
        self._columns = columns
        self._pixels = pixels
        self._header_click_map = header_click_map or {}
        self._on_drag_start = on_drag_start
        self._cells: dict[str, tk.Frame] = {}
        self._labels: dict[str, tk.Label] = {}
        self._build()
        self._bind_clicks()

    def _build(self):
        for idx, col in enumerate(self._columns):
            self.grid_columnconfigure(idx, minsize=self._pixels.get(col, 80))
            cell = tk.Frame(self, bg="#e8e8e8")
            lbl = tk.Label(cell, text=col, font=FONT_BODY_BOLD, bg="#e8e8e8",
                           fg=TEXT_PRIMARY, anchor="w", padx=8, wraplength=0)
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
        for col, callback in self._header_click_map.items():
            lbl = self._labels.get(col)
            if lbl:
                lbl.config(cursor="hand2")
                lbl.bind("<Button-1>", lambda e, c=col: callback(c))

    def refresh_widths(self, pixels: dict[str, int]):
        self._pixels = pixels
        for idx, col in enumerate(self._columns):
            self.grid_columnconfigure(idx, minsize=pixels.get(col, 80))
            lbl = self._labels.get(col)
            if lbl:
                lbl.config(wraplength=max(pixels.get(col, 80) - 16, 8))
