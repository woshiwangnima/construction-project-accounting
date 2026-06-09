"""通用 UI 工具与可复用 widget。"""

import tkinter as tk
from tkinter import ttk
from datetime import datetime

from ..theme import (
    APP_BG, ACCENT, ACCENT_HOVER, DANGER,
    FONT_BODY, FONT_BUTTON, FONT_SMALL,
)


def _make_scrollable(parent, height=None):
    canvas = tk.Canvas(parent, borderwidth=0, highlightthickness=0, height=height,
                       bg=parent.cget("bg") if isinstance(parent, tk.Frame) else APP_BG)
    scrollbar = ttk.Scrollbar(parent, orient=tk.VERTICAL, command=canvas.yview)
    canvas.configure(yscrollcommand=scrollbar.set)
    frame = ttk.Frame(canvas)
    frame.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
    win_id = canvas.create_window((0, 0), window=frame, anchor="nw")
    canvas.bind("<Configure>", lambda e, wid=win_id: canvas.itemconfig(wid, width=e.width), add="+")
    canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
    scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
    return canvas, scrollbar, frame


def _make_btn(parent, text, cmd, style="primary", width=None):
    colors = {
        "primary": (ACCENT, "white"),
        "danger": (DANGER, "white"),
        "secondary": ("#4a5568", "white"),
        "ghost": ("#edf2f7", "#2d3748"),
    }
    bg, fg = colors.get(style, colors["primary"])
    btn = tk.Button(parent, text=text, command=cmd, font=FONT_BUTTON,
                    bg=bg, fg=fg, activebackground=ACCENT_HOVER, activeforeground="white",
                    relief="raised", bd=2, padx=20, pady=10, cursor="hand2")
    if width:
        btn.config(width=width)
    hover_bg = ACCENT_HOVER if style == "primary" else ("#e2e8f0" if style == "ghost" else bg)
    btn.bind("<Enter>", lambda e: btn.config(bg=hover_bg))
    btn.bind("<Leave>", lambda e: btn.config(bg=bg))
    return btn


def _set_btn_state(btn, disabled: bool) -> None:
    """设置按钮 disabled 状态，兼容 tk.Button 和 ttk.Widget。

    tk.Button 用 config(state=...)；ttk.Widget 用 state(['disabled'])。
    出错时静默吞掉（不影响主流程）。
    """
    try:
        if hasattr(btn, "state") and callable(getattr(btn, "state", None)):
            # ttk
            if disabled:
                btn.state(["disabled"])
            else:
                btn.state(["!disabled"])
        else:
            btn.config(state="disabled" if disabled else "normal")
    except Exception:
        pass


def _input_entry(parent, value="", placeholder="", width=30):
    var = tk.StringVar(value=value)
    entry = ttk.Entry(parent, textvariable=var, font=FONT_BODY, width=width)
    if placeholder and not value:
        entry.insert(0, placeholder)
        entry.config(foreground="gray")

        def on_focus_in(e):
            if entry.get() == placeholder:
                entry.delete(0, tk.END)
                entry.config(foreground="black")

        def on_focus_out(e):
            if not entry.get():
                entry.insert(0, placeholder)
                entry.config(foreground="gray")

        entry.bind("<FocusIn>", on_focus_in)
        entry.bind("<FocusOut>", on_focus_out)
    return entry, var


class DatePicker(ttk.Frame):
    """年-月-日三段式日期选择器，月和日允许 `--` 表示不指定。"""

    def __init__(self, parent, **kwargs):
        super().__init__(parent, **kwargs)
        now = datetime.now()

        years = [str(y) for y in range(now.year - 20, now.year + 21)]
        # 与「工作类型」下拉保持一致：闭合态用 FONT_BODY
        self.year_cb = ttk.Combobox(self, values=years, width=6,
                                    font=FONT_BODY, state="readonly")
        self.year_cb.set(str(now.year))
        self.year_cb.pack(side=tk.LEFT)
        ttk.Label(self, text="年", font=FONT_BODY).pack(side=tk.LEFT, padx=2)

        months = ["--"] + [f"{m:02d}" for m in range(1, 13)]
        self.month_cb = ttk.Combobox(self, values=months, width=3,
                                     font=FONT_BODY, state="readonly")
        self.month_cb.set("--")
        self.month_cb.pack(side=tk.LEFT)
        ttk.Label(self, text="月", font=FONT_BODY).pack(side=tk.LEFT, padx=2)

        days = ["--"] + [f"{d:02d}" for d in range(1, 32)]
        self.day_cb = ttk.Combobox(self, values=days, width=3,
                                   font=FONT_BODY, state="readonly")
        self.day_cb.set("--")
        self.day_cb.pack(side=tk.LEFT)
        ttk.Label(self, text="日", font=FONT_BODY).pack(side=tk.LEFT, padx=2)

    def get(self):
        return f"{self.year_cb.get()}-{self.month_cb.get()}-{self.day_cb.get()}"

    def set(self, date_str):
        if not date_str:
            return
        parts = date_str.split("-")
        if len(parts) >= 1 and parts[0]:
            self.year_cb.set(parts[0])
        if len(parts) >= 2 and parts[1]:
            self.month_cb.set(parts[1])
        if len(parts) >= 3 and parts[2]:
            self.day_cb.set(parts[2])


class DateTypeSelector(ttk.Frame):
    """三模态日期选择器：无时间 / 单个时间 / 起止时间。

    `.get()` 返回 `(type, start, end)`；`type` 只能为 `DATE_TYPES` 之一。
    """

    DATE_TYPES = ["单个时间", "起止时间", "无时间"]

    def __init__(self, parent, default_type="无时间", default_start="", default_end="", **kwargs):
        super().__init__(parent, **kwargs)

        # 「时间类型」下拉：闭合态用 FONT_BODY 与「工作类型」保持一致
        self.date_type_cb = ttk.Combobox(self, values=self.DATE_TYPES,
                                         font=FONT_BODY, state="readonly")
        dt = default_type if default_type in self.DATE_TYPES else "无时间"
        self.date_type_cb.set(dt)
        self.date_type_cb.pack(fill=tk.X)
        self.date_type_cb.bind("<<ComboboxSelected>>", self._on_change)

        self.date_container = ttk.Frame(self)
        self.date_container.pack(fill=tk.X, pady=(4, 0))

        self.single_frame = ttk.Frame(self.date_container)
        ttk.Label(self.single_frame, text="日期：").pack(side=tk.LEFT)
        self.single_date = DatePicker(self.single_frame)
        self.single_date.pack(side=tk.LEFT, padx=(4, 0))
        self.single_date.set(default_start)

        self.range_frame = ttk.Frame(self.date_container)
        ttk.Label(self.range_frame, text="起").pack(side=tk.LEFT)
        self.start_date = DatePicker(self.range_frame)
        self.start_date.pack(side=tk.LEFT, padx=(4, 12))
        ttk.Label(self.range_frame, text="止").pack(side=tk.LEFT)
        self.end_date = DatePicker(self.range_frame)
        self.end_date.pack(side=tk.LEFT, padx=(4, 0))
        self.end_date.set(default_end)

        self.none_frame = ttk.Frame(self.date_container)
        self._on_change()

    def _on_change(self, event=None):
        dt = self.date_type_cb.get()
        for f in (self.single_frame, self.range_frame, self.none_frame):
            f.pack_forget()
        if dt == "单个时间":
            self.single_frame.pack(fill=tk.X)
        elif dt == "起止时间":
            self.range_frame.pack(fill=tk.X)

    def get(self):
        dt = self.date_type_cb.get()
        s = e = ""
        if dt == "单个时间":
            s = self.single_date.get()
        elif dt == "起止时间":
            s = self.start_date.get()
            e = self.end_date.get()
        return dt, s, e

    def set(self, date_type, start="", end=""):
        self.date_type_cb.set(date_type if date_type in self.DATE_TYPES else "无时间")
        self.single_date.set(start)
        self.start_date.set(start)
        self.end_date.set(end)
        self._on_change()


class RowActionButtons(tk.Frame):
    """可复用的行操作按钮组：上移 / 下移 / 删除。

    设计目标：让账单列表、工种列表、未来其它行项目都能复用。
    用 `set_enabled` 按行上下文禁用按钮（首行禁上移、末行禁下移）。

    参数：
        parent: 父容器
        on_move_up / on_move_down / on_delete: 三个回调
        labels: 三按钮文本，默认 ("上移", "下移", "删除")
        button_width: 按钮字符宽度，默认 4
    """

    def __init__(
        self,
        parent,
        on_move_up=None,
        on_move_down=None,
        on_delete=None,
        labels=("上移", "下移", "删除"),
        button_width: int = 4,
        **kwargs,
    ):
        bg = kwargs.pop("bg", APP_BG)
        super().__init__(parent, bg=bg, **kwargs)
        self._buttons: dict[str, tk.Button] = {}
        for key, label, cmd in (
            ("up", labels[0], on_move_up),
            ("down", labels[1], on_move_down),
            ("delete", labels[2], on_delete),
        ):
            fg = "#c0392b" if key == "delete" else "#2d3748"
            b = tk.Button(
                self,
                text=label,
                font=FONT_SMALL,
                width=button_width,
                command=cmd,
                bg="white",
                fg=fg,
                activebackground="#edf2f7",
                activeforeground=fg,
                relief="groove",
                bd=1,
                cursor="hand2",
                padx=2,
                pady=0,
            )
            b.pack(side=tk.LEFT, padx=1)
            self._buttons[key] = b

    def set_enabled(self, move_up: bool = True, move_down: bool = True, delete: bool = True) -> None:
        """按上下文启用/禁用按钮（首行禁上移、末行禁下移等）。"""
        self._buttons["up"].config(state=tk.NORMAL if move_up else tk.DISABLED)
        self._buttons["down"].config(state=tk.NORMAL if move_down else tk.DISABLED)
        self._buttons["delete"].config(state=tk.NORMAL if delete else tk.DISABLED)


__all__ = [
    "_make_scrollable",
    "_make_btn",
    "_input_entry",
    "DatePicker",
    "DateTypeSelector",
    "RowActionButtons",
    "ListViewBase",
    "BillListView",
    "WorkerListView",
]


def __getattr__(name):
    """PEP 562：延迟加载重量级 widget，避免 widgets 包初始化时触发 content 模块循环导入。"""
    if name == "ListViewBase":
        from .list_view_base import ListViewBase as _LVB
        return _LVB
    if name == "BillListView":
        from .bill_list_view import BillListView as _BLV
        return _BLV
    if name == "WorkerListView":
        from .worker_list_view import WorkerListView as _WLV
        return _WLV
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")

