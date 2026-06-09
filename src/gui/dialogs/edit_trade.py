"""编辑/添加工作项目对话框。

UI 风格与「添加记录」对话框保持一致：
- 滚动包裹框（canvas + scrollbar），鼠标滚轮可滚动
- 各字段 label + ttk.Combobox / ttk.Entry 风格与 EditBillDialog 对齐
- 取消/确认按钮放在 content_frame 底部
"""
import tkinter as tk
from tkinter import ttk, messagebox

from ..theme import (
    APP_BG, TEXT_PRIMARY, TEXT_SECONDARY,
    FONT_BODY, FONT_BODY_BOLD, FONT_SMALL,
)
from ..widgets import _make_btn, _input_entry
from ...project_manager import update_project
from ...billing import Billing, read_billing, write_billing
from ...trade_item_id import ensure_trade_item_id


BILLING_TYPES = ["按单价", "无单价"]


class EditTradeItemDialog:
    def __init__(self, parent, item, categories, units, project, ref, on_done, editable=True):
        self.item = item
        self.project = project
        self.ref = ref
        self.on_done = on_done
        self._editable = editable

        dialog = tk.Toplevel(parent)
        dialog.title("编辑工作项目")
        dialog.transient(parent)
        dialog.grab_set()
        dialog.configure(bg=APP_BG)
        # 统一所有下拉框弹层（Listbox）字号：需在所有 Combobox 创建前设置才生效
        dialog.option_add("*TCombobox*Listbox.font", ("Microsoft YaHei UI", 14))

        w, h = 600, 540
        x = parent.winfo_rootx() + (parent.winfo_width() - w) // 2
        y = parent.winfo_rooty() + (parent.winfo_height() - h) // 2
        # 确保弹窗不超出屏幕
        screen_h = parent.winfo_screenheight()
        if y + h > screen_h - 40:
            y = max(20, screen_h - h - 40)
        dialog.geometry(f"{w}x{h}+{x}+{y}")
        dialog.minsize(max(520, w - 60), max(420, h - 80))
        dialog.resizable(True, True)

        # ── 滚动包裹框：所有元素都放进 content_frame 内，超出可滚 ──
        wrap = tk.Frame(dialog, bg=APP_BG)
        wrap.pack(fill=tk.BOTH, expand=True)
        canvas = tk.Canvas(wrap, borderwidth=0, highlightthickness=0, bg=APP_BG)
        scrollbar = ttk.Scrollbar(wrap, orient=tk.VERTICAL, command=canvas.yview)
        canvas.configure(yscrollcommand=scrollbar.set)
        content_frame = tk.Frame(canvas, bg=APP_BG)
        content_frame.bind(
            "<Configure>",
            lambda e: canvas.configure(scrollregion=canvas.bbox("all")),
        )
        canvas_win = canvas.create_window((0, 0), window=content_frame, anchor="nw")
        canvas.bind(
            "<Configure>",
            lambda e, w=canvas_win: canvas.itemconfig(w, width=e.width),
        )
        canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        # 让鼠标在 content_frame 上滚轮时驱动滚动条（Windows / macOS / Linux 三套事件）
        def _on_wheel(e):
            sr = canvas.cget("scrollregion")
            try:
                _, y1, _, y2 = map(float, sr.split())
            except (ValueError, tk.TclError):
                return
            if y2 - y1 <= canvas.winfo_height():
                return
            delta = -1 * (e.delta / 120) if e.delta else 0
            canvas.yview_scroll(int(delta), "units")

        def _wheel_up(_):
            _on_wheel(type("E", (), {"delta": 120})())

        def _wheel_down(_):
            _on_wheel(type("E", (), {"delta": -120})())

        # 给滚动框内所有子控件（递归）也绑滚轮事件，
        # 解决「必须滚到滚动条上才生效」的问题
        def _bind_wheel_recursive(widget):
            widget.bind("<MouseWheel>", _on_wheel, add="+")
            widget.bind("<Button-4>", _wheel_up, add="+")
            widget.bind("<Button-5>", _wheel_down, add="+")
            for child in widget.winfo_children():
                _bind_wheel_recursive(child)
        _bind_wheel_recursive(content_frame)

        # ── 业务字段 ──

        # 工作类型：下拉（样式与「选择工作项目」一致）
        tk.Label(content_frame, text="\U0001f527 工作类型", font=FONT_BODY_BOLD,
                 bg=APP_BG).pack(pady=(16, 4), padx=20, anchor="w")
        self.cat_var = tk.StringVar(value=item.get("category", ""))
        self.cat_cb = ttk.Combobox(content_frame, values=categories,
                                    textvariable=self.cat_var,
                                    font=FONT_BODY, state="readonly")
        self.cat_cb.pack(fill=tk.X, padx=20)
        if categories and not self.cat_var.get():
            self.cat_cb.set(categories[0])

        # 工作名称：label + entry
        tk.Label(content_frame, text="\U0001f4dd 工作名称", font=FONT_BODY_BOLD,
                 bg=APP_BG).pack(pady=(12, 4), padx=20, anchor="w")
        self.name_var = tk.StringVar(value=item.get("name", ""))
        name_e, _ = _input_entry(content_frame)
        name_e.config(textvariable=self.name_var, width=40)
        name_e.pack(fill=tk.X, padx=20)

        # 计费类型：下拉（样式与「日期」栏一致：下拉 + 联动容器）
        tk.Label(content_frame, text="\U0001f4b0 计费类型", font=FONT_BODY_BOLD,
                 bg=APP_BG).pack(pady=(12, 4), padx=20, anchor="w")
        # 初始值由 Billing.from_dict 决定（缺 has_unit 时按 True）
        self.is_per_unit_var = tk.StringVar(
            value="按单价" if read_billing(item).is_per_unit else "无单价"
        )
        self.billing_cb = ttk.Combobox(
            content_frame, values=BILLING_TYPES,
            textvariable=self.is_per_unit_var,
            font=FONT_BODY, state="readonly",
        )
        self.billing_cb.pack(fill=tk.X, padx=20)
        self.billing_cb.bind("<<ComboboxSelected>>", lambda e: self._toggle_price())
        self._ensure_valid_billing_value()

        # 按单价时显示的「单价 + 单位」容器（先建 frame，pack 留到 _toggle_price）
        self.price_frame = tk.Frame(content_frame, bg=APP_BG)

        tk.Label(self.price_frame, text="单价", font=FONT_BODY_BOLD,
                 bg=APP_BG).grid(row=0, column=0, sticky="w", pady=2)
        # 单价：新增模式固定 1；编辑既有条目时取 Billing 解析值
        default_billing = read_billing(item)
        if not item.get("name"):  # 新增模式
            default_price = 1
        else:
            default_price = default_billing.unit_price
        self.price_var = tk.StringVar(value=str(default_price))
        price_e, _ = _input_entry(self.price_frame)
        price_e.config(textvariable=self.price_var, width=10)
        price_e.grid(row=0, column=1, sticky="w", padx=(8, 0), pady=2)

        tk.Label(self.price_frame, text="单位", font=FONT_BODY_BOLD,
                 bg=APP_BG).grid(row=1, column=0, sticky="w", pady=(8, 2))
        self.unit_var = tk.StringVar(value=default_billing.unit)
        # 既可输入又可下拉：用 ttk.Combobox 默认 state（normal），可编辑
        self.unit_cb = ttk.Combobox(self.price_frame, values=units,
                                     textvariable=self.unit_var,
                                     font=FONT_BODY)
        self.unit_cb.grid(row=1, column=1, sticky="ew", padx=(8, 0), pady=(8, 2))
        self.price_frame.grid_columnconfigure(1, weight=1)

        # 底部按钮（取消/确定）放在 content_frame 末尾，跟着滚动
        self._btn_frame = tk.Frame(content_frame, bg=APP_BG)
        self._btn_frame.pack(pady=(24, 16))
        _make_btn(self._btn_frame, "取消", dialog.destroy, "ghost").pack(side=tk.LEFT, padx=4)
        self._save_btn = _make_btn(self._btn_frame, "确定", lambda: self._confirm(dialog),
                                    "primary")
        self._save_btn.pack(side=tk.LEFT, padx=4)
        if not self._editable:
            from ..widgets import _set_btn_state
            _set_btn_state(self._save_btn, True)
            _set_btn_state(name_e, True)

        # 初始按当前值决定容器显隐（_btn_frame 已建好，pack 会固定在按钮上方）
        self._toggle_price()

        self._dialog = dialog

    def _ensure_valid_billing_value(self):
        """容错：item 中存的是旧「按单价计费 / 无单价计费」时也归一为新值。"""
        cur = self.is_per_unit_var.get()
        if cur not in BILLING_TYPES:
            if cur == "按单价计费":
                self.is_per_unit_var.set("按单价")
            elif cur == "无单价计费":
                self.is_per_unit_var.set("无单价")
            else:
                self.is_per_unit_var.set("按单价")

    def _toggle_price(self):
        """「按单价」→ 显示单价+单位容器；「无单价」→ 隐藏。

        必须用 before=self._btn_frame 显式指定位置，否则 pack_forget + pack
        会把 price_frame 追加到 pack 顺序末尾（btn_frame 之后），
        导致「单价/单位」跑到「取消/确定」按钮下面。
        """
        self._ensure_valid_billing_value()
        if self.is_per_unit_var.get() == "按单价":
            self.price_frame.pack(fill=tk.X, padx=20, pady=(8, 0),
                                   before=self._btn_frame)
        else:
            self.price_frame.pack_forget()

    def _confirm(self, dialog):
        if not self._editable:
            return
        name = self.name_var.get().strip()
        if not name:
            messagebox.showwarning("提示", "请输入工作名称", parent=dialog)
            return

        is_per_unit = self.is_per_unit_var.get() == "按单价"
        price = 1
        unit = ""
        if is_per_unit:
            try:
                price = float(self.price_var.get())
            except ValueError:
                messagebox.showwarning("提示", "单价请输入数字", parent=dialog)
                return
            unit = self.unit_var.get().strip()
            if not unit:
                messagebox.showwarning("提示", "请输入或选择单位", parent=dialog)
                return

        self.item["category"] = self.cat_var.get()
        ensure_trade_item_id(self.item)
        self.item["name"] = name
        # 计费三件套：组装 Billing 后一次性写回（__post_init__ 会自动归一化）
        write_billing(self.item, Billing(
            has_unit=is_per_unit,
            unit_price=price,
            unit=unit,
        ))

        if self.item not in self.project.get("trade_items", []):
            self.project.setdefault("trade_items", []).append(self.item)

        update_project(self.ref, self.project)
        dialog.destroy()
        if self.on_done:
            self.on_done()
