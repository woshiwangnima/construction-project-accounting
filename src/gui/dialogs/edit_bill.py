"""编辑账单记录对话框"""

import tkinter as tk
from tkinter import ttk, messagebox
from datetime import datetime

from ..theme import (
    APP_BG, ACCENT, DANGER, TEXT_PRIMARY, TEXT_SECONDARY,
    FONT_BODY, FONT_BODY_BOLD, FONT_SMALL, FONT_HEADING, FONT_CALC_BTN,
)
from ..widgets import _make_btn, _input_entry, DateTypeSelector
from ...config_loader import load_app
from ...calculator import (
    MathParseError,
    evaluate_canonical,
    to_canonical,
    to_display,
)
from ...project_manager import update_project, ensure_bill_id
from ...voice import get_voice, KEYSYM_TO_KEY
from ...symbol_mapping import voice_key_for_char
from ...billing import read_billing
from ...billing_resolver import resolve_trade_item, is_orphan, resolve_billing, resolve_label
from ...bill_recompute import recompute_bill_total
from ...bill_review import copy_reviewed_state
from ...trade_item_id import ensure_trade_item_id


def _format_number(value: float) -> str:
    text = f"{value:.10f}".rstrip("0").rstrip(".")
    return text or "0"


def _formula_result_text(content: str, op_map: dict) -> str:
    content = (content or "").strip()
    if not content:
        return ""
    try:
        canonical = to_canonical(content, op_map)
        result = evaluate_canonical(canonical)
    except MathParseError:
        return "结果：错误"
    return f"结果：{_format_number(result)}"


class EditBillDialog:
    def __init__(self, parent, project, on_done, bill=None, editable=True):
        self.project = project
        self.on_done = on_done
        self.result = None
        self._trade_items = project.get("trade_items", [])
        self._existing_bill = bill  # 编辑模式时保存原记录引用
        self._editable = editable
        self._orphan_on_open = False
        self._orphan_label = None

        dialog = tk.Toplevel(parent)
        dialog.title("编辑记录" if bill else "添加记录")
        dialog.transient(parent)
        dialog.grab_set()
        dialog.configure(bg=APP_BG)
        # 统一所有下拉框弹层（Listbox）字号：需在所有 Combobox 创建前设置才生效
        dialog.option_add("*TCombobox*Listbox.font", ("Microsoft YaHei UI", 14))

        cfg = load_app()
        op_map = cfg.get("symbol_mapping", {})
        sizes = cfg.get("window_sizes", {}) or {}
        eb_size = sizes.get("edit_bill") or [720, 900]
        w, h = int(eb_size[0]), int(eb_size[1])
        x = parent.winfo_rootx() + (parent.winfo_width() - w) // 2
        y = parent.winfo_rooty() + (parent.winfo_height() - h) // 2
        # 确保弹窗不超出屏幕
        screen_h = parent.winfo_screenheight()
        if y + h > screen_h - 40:
            y = max(20, screen_h - h - 40)
        dialog.geometry(f"{w}x{h}+{x}+{y}")
        dialog.minsize(max(680, w - 40), max(820, h - 80))
        # 允许纵横缩放
        dialog.resizable(True, True)

        # 关闭时停止 TTS 朗读（pyttsx3 引擎在另一线程，停不掉的播报会一直响）
        voice = get_voice()
        def _on_close():
            voice.stop()
            dialog.destroy()
        dialog.protocol("WM_DELETE_WINDOW", _on_close)

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
        tk.Label(content_frame, text="\U0001f527 选择工作项目", font=FONT_BODY_BOLD,
                 bg=APP_BG).pack(pady=(16, 4), padx=20, anchor="w")
        item_labels = [f"{ti['category']} - {ti['name']}" for ti in self._trade_items]
        self.trade_cb = ttk.Combobox(content_frame, values=item_labels,
                                     font=FONT_BODY, state="readonly")
        self.trade_cb.pack(fill=tk.X, padx=20)

        # 编辑模式：用 trade_item_id 找到对应 trade item，预选 combobox
        if bill:
            pre_ti = resolve_trade_item(bill, self._trade_items)
            if pre_ti is not None:
                label = f"{pre_ti['category']} - {pre_ti['name']}"
                if label in item_labels:
                    self.trade_cb.set(label)
            elif is_orphan(bill):
                # 孤儿账单：让用户必须先选新 trade item
                self._orphan_on_open = True
                self._orphan_label = tk.StringVar(value="⚠ 引用的工作已删除/重命名，请重新选择")
                tk.Label(content_frame, textvariable=self._orphan_label,
                         font=FONT_SMALL, bg=APP_BG, fg=DANGER).pack(
                    pady=(0, 4), padx=20, anchor="w")
        self.trade_cb.bind("<<ComboboxSelected>>", lambda e: self._handle_trade_selection(op_map))

        # 类别 + 单价 同行
        info_frame = tk.Frame(content_frame, bg=APP_BG)
        info_frame.pack(fill=tk.X, padx=20, pady=(8, 0))
        self.info_cat = tk.StringVar()
        self.info_price = tk.StringVar()
        tk.Label(info_frame, textvariable=self.info_cat, font=FONT_SMALL,
                 bg=APP_BG, fg=TEXT_SECONDARY).pack(side=tk.LEFT)
        tk.Label(info_frame, textvariable=self.info_price, font=FONT_SMALL,
                 bg=APP_BG, fg=TEXT_SECONDARY).pack(side=tk.LEFT, padx=(20, 0))

        # 公式输入区
        tk.Label(content_frame, text="\U0001f522 输入计算公式",
                 font=FONT_BODY_BOLD, bg=APP_BG).pack(pady=(12, 4), padx=20, anchor="w")

        self.content_var = tk.StringVar(value=bill.get("content", "") if bill else "")
        entry = ttk.Entry(content_frame, textvariable=self.content_var,
                          font=("Microsoft YaHei UI", 18))
        entry.pack(fill=tk.X, padx=20, pady=(0, 6), ipady=6)
        self._entry = entry

        # Calculator-style button panel
        calc_frame = tk.Frame(content_frame, bg=APP_BG, padx=20)
        calc_frame.pack(fill=tk.X)

        def _ins(s):
            voice.play_key(voice_key_for_char(s, op_map) or s)
            entry.insert(tk.INSERT, s)
            entry.focus_set()

        def _clear():
            voice.play_key("清空")
            self.content_var.set("")
            entry.focus_set()

        def _backspace():
            voice.play_key("删除")
            cur = self.content_var.get()
            if cur:
                self.content_var.set(cur[:-1])
            entry.focus_set()

        # 键盘输入 → 同步播报
        def _on_key_press(e):
            key = voice_key_for_char(e.char, op_map) if getattr(e, "char", "") else None
            if not key:
                key = KEYSYM_TO_KEY.get(e.keysym)
            if key:
                voice.play_key(key)
        entry.bind("<KeyPress>", _on_key_press, add="+")

        # 4 行 × 5 列；第 4 行第 3 列空着，让 0/./+ 与上方 1/2/3 对齐
        # 颜色：数字灰、运算符/括号橙、清空/删除红
        COLOR_DIGIT = "#ecf0f1"
        COLOR_OP = "#fdebd0"
        COLOR_CTRL = "#fadbd8"
        rows = [
            [("7", COLOR_DIGIT), ("8", COLOR_DIGIT), ("9", COLOR_DIGIT), ("÷", COLOR_OP), ("(", COLOR_OP)],
            [("4", COLOR_DIGIT), ("5", COLOR_DIGIT), ("6", COLOR_DIGIT), ("×", COLOR_OP), (")", COLOR_OP)],
            [("1", COLOR_DIGIT), ("2", COLOR_DIGIT), ("3", COLOR_DIGIT), ("-", COLOR_OP), ("清空", COLOR_CTRL)],
            [("0", COLOR_DIGIT), (".", COLOR_DIGIT), None,            ("+", COLOR_OP), ("删除", COLOR_CTRL)],
        ]
        for r, row in enumerate(rows):
            for c, cell in enumerate(row):
                if cell is None:
                    # 留空格子以对齐上方数字键列宽
                    spacer = tk.Frame(calc_frame, bg=APP_BG)
                    spacer.grid(row=r, column=c, padx=3, pady=2, sticky="nsew")
                    continue
                text, color = cell
                if text == "清空":
                    cmd = _clear
                elif text == "删除":
                    cmd = _backspace
                else:
                    cmd = (lambda t=text: _ins(t))
                b = tk.Button(calc_frame, text=text, font=FONT_CALC_BTN, bg=color, fg=TEXT_PRIMARY,
                              bd=2, relief="raised", cursor="hand2",
                              command=cmd)
                b.grid(row=r, column=c, padx=3, pady=2, sticky="nsew")
        # 5 列等宽
        for c in range(5):
            calc_frame.grid_columnconfigure(c, weight=1, uniform="calc_cols")
        for r in range(4):
            calc_frame.grid_rowconfigure(r, weight=1)

        self.content_var.trace_add("write", lambda *_: self._update_display(op_map))

        # 标准公式展示：标签与内容分两行，标签右侧带 🔊 朗读按钮
        disp_header = tk.Frame(content_frame, bg=APP_BG)
        disp_header.pack(fill=tk.X, padx=20, pady=(12, 2))
        speak_icon = "\U0001f50a" if voice.enabled else "\U0001f507"
        tk.Label(disp_header, text="标准计算公式展示", font=FONT_SMALL,
                 bg=APP_BG, fg=TEXT_SECONDARY).pack(side=tk.LEFT)
        btn_speak = tk.Button(
            disp_header, text=speak_icon, font=FONT_BODY,
            bg=APP_BG, fg=ACCENT, relief="flat", cursor="hand2",
            activebackground=APP_BG,
            command=lambda: voice.speak_formula(self.display_var.get()),
        )
        btn_speak.pack(side=tk.LEFT, padx=(4, 0))
        self.formula_result_var = tk.StringVar()
        tk.Label(disp_header, textvariable=self.formula_result_var, font=FONT_SMALL,
                 bg=APP_BG, fg=DANGER).pack(side=tk.RIGHT)
        self.display_var = tk.StringVar()
        tk.Label(content_frame, textvariable=self.display_var, font=FONT_BODY,
                 bg=APP_BG, fg=TEXT_PRIMARY, wraplength=520, justify="left",
                 anchor="w").pack(pady=(0, 4), padx=20, fill=tk.X)

        # 金额（红色：标签 + 数字同行）
        amount_row = tk.Frame(content_frame, bg=APP_BG)
        amount_row.pack(pady=(8, 0), padx=20, anchor="w")
        tk.Label(amount_row, text="金额", font=FONT_BODY_BOLD,
                 bg=APP_BG, fg=DANGER).pack(side=tk.LEFT)
        self.total_var = tk.StringVar()
        tk.Label(amount_row, textvariable=self.total_var, font=FONT_HEADING,
                 bg=APP_BG, fg=DANGER).pack(side=tk.LEFT, padx=(12, 0))

        # 备注
        tk.Label(content_frame, text="\U0001f4ac 备注（可选）", font=FONT_BODY_BOLD,
                 bg=APP_BG).pack(pady=(8, 4), padx=20, anchor="w")
        self.note_var = tk.StringVar(value=bill.get("note", "") if bill else "")
        note_e, _ = _input_entry(content_frame)
        note_e.config(textvariable=self.note_var, width=40)
        note_e.pack(fill=tk.X, padx=20)

        # 日期
        tk.Label(content_frame, text="\U0001f4c5 日期", font=FONT_BODY_BOLD,
                 bg=APP_BG).pack(pady=(8, 4), padx=20, anchor="w")
        date_frame = tk.Frame(content_frame, bg=APP_BG)
        date_frame.pack(fill=tk.X, padx=20)
        if bill:
            default_type = bill.get("work_date_type", "单个时间" if bill.get("work_date_start") else "无时间")
            default_start = bill.get("work_date_start", "")
            default_end = bill.get("work_date_end", "")
            if default_type not in DateTypeSelector.DATE_TYPES:
                default_type = "无时间"
        else:
            # 添加模式：日期默认"无时间"，不自动填当天
            default_type = "无时间"
            default_start = ""
            default_end = ""
        self.date_selector = DateTypeSelector(
            date_frame,
            default_type=default_type,
            default_start=default_start,
            default_end=default_end,
        )
        self.date_selector.pack(fill=tk.X)

        # 底部按钮（取消/确定）走 _on_close 统一关闭（先 stop voice 再 destroy）
        btn_frame = tk.Frame(content_frame, bg=APP_BG)
        btn_frame.pack(pady=(20, 16))
        _make_btn(btn_frame, "取消", _on_close, "ghost").pack(side=tk.LEFT, padx=4)
        self._save_btn = _make_btn(btn_frame, "确定", lambda: self._confirm(dialog, op_map, voice),
                                    "primary")
        self._save_btn.pack(side=tk.LEFT, padx=4)
        if not self._editable:
            from ..widgets import _set_btn_state
            _set_btn_state(self._save_btn, True)

        self._update_display(op_map)
        self._dialog = dialog

    def _handle_trade_selection(self, op_map):
        if self._orphan_on_open and self._orphan_label is not None:
            self._orphan_label.set("")
        self._update_display(op_map)

    def _get_selected_item(self):
        selected = self.trade_cb.get().strip()
        for ti in self._trade_items:
            if f"{ti['category']} - {ti['name']}" == selected:
                return ti
        return None

    def _insert_sym(self, sym, entry):
        entry.insert(tk.INSERT, sym)
        entry.focus_set()

    def _update_display(self, op_map):
        ti = self._get_selected_item()
        content = self.content_var.get().strip()
        self.formula_result_var.set(_formula_result_text(content, op_map))

        canonical = None
        display_text = ""
        parse_error = None
        if content:
            try:
                canonical = to_canonical(content, op_map)
                display_text = to_display(canonical)
            except MathParseError as exc:
                parse_error = str(exc)

        if not ti:
            self.info_cat.set("")
            self.info_price.set("")
            self.total_var.set("")
            if parse_error:
                self.display_var.set(f"公式错误：{parse_error}")
            elif display_text:
                self.display_var.set(display_text)
            else:
                self.display_var.set("")
            return

        self.info_cat.set(f"类别：{ti['category']}")
        ti_billing = read_billing(ti)
        if ti_billing.is_per_unit:
            self.info_price.set(f"单价：{ti_billing.unit_price:.2f} {ti_billing.unit}")
        else:
            self.info_price.set("无单价计费")

        if not content:
            self.display_var.set("")
            self.total_var.set("")
            return

        if parse_error:
            self.display_var.set(f"公式错误：{parse_error}")
            self.total_var.set("请输入有效算式")
            return

        self.display_var.set(display_text)
        try:
            result = evaluate_canonical(canonical)
        except MathParseError as exc:
            self.display_var.set(f"公式错误：{exc}")
            self.total_var.set("请输入有效算式")
            return

        if ti_billing.is_per_unit:
            total = round(result * ti_billing.unit_price, 2)
        else:
            total = round(result, 2)
        self.total_var.set(f"￥{total:.2f}")

    def _confirm(self, dialog, op_map, voice):
        if not self._editable:
            return
        selected = self.trade_cb.get().strip()
        if not selected:
            messagebox.showwarning("提示", "请选择工作项目", parent=dialog)
            return
        content_raw = self.content_var.get().strip()
        if not content_raw:
            messagebox.showwarning("提示", "请输入计算公式", parent=dialog)
            return

        # 日期（三种模式之一）
        date_type, date_start, date_end = self.date_selector.get()
        try:
            canonical = to_canonical(content_raw, op_map)
            evaluate_canonical(canonical)  # 校验
        except MathParseError as exc:
            messagebox.showwarning("公式错误", f"无法解析公式：\n{exc}", parent=dialog)
            return

        ti = self._get_selected_item()
        if ti is None:
            messagebox.showwarning("提示", "请选择有效的工作项目", parent=dialog)
            return
        trade_item_id = ensure_trade_item_id(ti)

        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        # 新版账单结构：只存 trade_item_id + 用户输入字段，不再存 trade_item_name / 价格 / total
        bill = {
            "trade_item_id": trade_item_id,
            "content": content_raw,
            "note": self.note_var.get().strip(),
            "work_date_type": date_type,
            "work_date_start": date_start,
            "work_date_end": date_end,
            "record_time": now,
            "reviewed": False,
        }
        # 保留 own id（编辑模式继承，新建模式重算）
        if self._existing_bill is not None and self._existing_bill.get("id"):
            bill["id"] = self._existing_bill["id"]
        copy_reviewed_state(self._existing_bill, bill)
        # 旧版遗留字段（trade_item_name / category / has_unit / unit_price / unit / total）
        # 在新版中彻底不再写——下次读盘时迁移函数会忽略它们

        # 若原 bill 是孤儿且这次有重选 trade item，清掉 frozen_snapshot
        if self._existing_bill is not None and is_orphan(self._existing_bill):
            bill.pop("frozen_snapshot", None)
            bill.pop("frozen_total", None)
            bill.pop("_needs_attention", None)

        bills = self.project.setdefault("bills", [])
        if self._existing_bill is not None:
            # 编辑模式：原地更新已有记录
            self._existing_bill.clear()
            self._existing_bill.update(bill)
        else:
            # 新增模式：追加新记录
            ensure_bill_id(bill)
            bills.append(bill)

        update_project(self.project["_path"], self.project)
        voice.stop()
        dialog.destroy()
        if self.on_done:
            self.on_done()
