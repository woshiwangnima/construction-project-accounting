"""全局 ttk 主题配置（clam）"""

import tkinter as tk
from tkinter import ttk

from .theme import (
    ACCENT,
    APP_BG,
    BORDER,
    HIGHLIGHT_BG,
    ROW_STRIPE,
    TABLE_HEADER_BG,
    TABLE_HEADER_FG,
    TEXT_PRIMARY,
    TEXT_SECONDARY,
    TEXT_TERTIARY,
)


def apply_ttk_theme():
    """幂等配置全局 ttk 样式，可安全重复调用。"""
    try:
        s = ttk.Style()
        try:
            if s.theme_use() != "clam":
                s.theme_use("clam")
        except tk.TclError:
            pass

        from .font_manager import font_manager
        body = font_manager.get("body")
        tree = font_manager.get("tree")
        tree_header = font_manager.get("tree_header")

        try:
            s.configure(
                "TCombobox",
                fieldbackground=APP_BG,
                background=APP_BG,
                foreground=TEXT_PRIMARY,
                bordercolor=BORDER,
                arrowcolor=TEXT_SECONDARY,
                lightcolor=BORDER,
                darkcolor=BORDER,
                focuscolor=ACCENT,
                selectbackground=HIGHLIGHT_BG,
                selectforeground=TEXT_PRIMARY,
                padding=(8, 4),
                font=body,
            )
        except tk.TclError:
            pass

        try:
            s.configure(
                "TEntry",
                fieldbackground=APP_BG,
                background=APP_BG,
                foreground=TEXT_PRIMARY,
                bordercolor=BORDER,
                lightcolor=BORDER,
                darkcolor=BORDER,
                focuscolor=ACCENT,
                selectbackground=HIGHLIGHT_BG,
                selectforeground=TEXT_PRIMARY,
                padding=(8, 4),
                font=body,
            )
        except tk.TclError:
            pass

        try:
            s.configure(
                "TSpinbox",
                fieldbackground=APP_BG,
                background=APP_BG,
                foreground=TEXT_PRIMARY,
                bordercolor=BORDER,
                arrowcolor=TEXT_SECONDARY,
                lightcolor=BORDER,
                darkcolor=BORDER,
                focuscolor=ACCENT,
                selectbackground=HIGHLIGHT_BG,
                selectforeground=TEXT_PRIMARY,
                padding=(8, 4),
                font=body,
            )
        except tk.TclError:
            pass

        try:
            s.configure(
                "Treeview",
                background=APP_BG,
                fieldbackground=APP_BG,
                foreground=TEXT_PRIMARY,
                rowheight=34,
                bordercolor=BORDER,
                lightcolor=BORDER,
                darkcolor=BORDER,
                font=tree,
            )
            s.map(
                "Treeview",
                background=[("selected", HIGHLIGHT_BG)],
                foreground=[("selected", ACCENT)],
            )
        except tk.TclError:
            pass

        try:
            s.configure(
                "Treeview.Heading",
                background=TABLE_HEADER_BG,
                foreground=TABLE_HEADER_FG,
                relief="flat",
                borderwidth=0,
                font=tree_header,
            )
        except tk.TclError:
            pass

        try:
            s.configure(
                "TScrollbar",
                background=TABLE_HEADER_BG,
                troughcolor=TABLE_HEADER_BG,
                bordercolor=TABLE_HEADER_BG,
                arrowcolor=TEXT_SECONDARY,
                lightcolor=TABLE_HEADER_BG,
                darkcolor=TABLE_HEADER_BG,
            )
            s.map("TScrollbar", background=[("active", TEXT_TERTIARY)])
        except tk.TclError:
            pass

        try:
            s.configure(
                "TCheckbutton",
                background=APP_BG,
                foreground=TEXT_PRIMARY,
                indicatorbackground=APP_BG,
                indicatorforeground=ACCENT,
                font=body,
            )
        except tk.TclError:
            pass

        try:
            s.configure(
                "TRadiobutton",
                background=APP_BG,
                foreground=TEXT_PRIMARY,
                indicatorbackground=APP_BG,
                indicatorforeground=ACCENT,
                font=body,
            )
        except tk.TclError:
            pass

        try:
            s.configure(
                "TProgressbar",
                background=ACCENT,
                troughcolor=ROW_STRIPE,
                bordercolor=BORDER,
            )
        except tk.TclError:
            pass

        try:
            s.configure(
                "TLabel",
                background=APP_BG,
                foreground=TEXT_PRIMARY,
            )
        except tk.TclError:
            pass

        try:
            s.configure(
                "TLabelframe",
                background=APP_BG,
                foreground=TEXT_PRIMARY,
                bordercolor=BORDER,
            )
        except tk.TclError:
            pass
    except tk.TclError:
        pass
