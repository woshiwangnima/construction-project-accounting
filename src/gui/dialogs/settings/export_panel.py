"""🖼 导出图片设置面板。

存储位置：user_config.json::export_defaults
UI 来自原 ExportSettingsDialog，重构为 ttk.Frame 面板。
"""

import tkinter as tk
from tkinter import ttk, colorchooser

from .base import BaseSettingsPanel, register_section
from ...theme import APP_BG, TEXT_PRIMARY, FONT_BODY, FONT_SMALL, FONT_BODY_BOLD
from ...widgets import _make_btn
from ....config_loader import load_user, save_user, load_app
from ....export_config import ExportDefaults, PriceListSettings, TextColors


@register_section
class ExportSettingsPanel(BaseSettingsPanel):
    section_id = "export"
    section_title = "导出图片"
    section_icon = "🖼"
    section_order = 20

    def _build(self):
        canvas, scrollbar, inner = self._make_scrollable()

        tk.Label(inner, text=f"{self.section_icon} 导出图片", font=FONT_BODY_BOLD,
                 bg=APP_BG, fg=TEXT_PRIMARY).pack(anchor="w", pady=(0, 12))

        # ── 价目表 ──────────────────────────────────────────────
        pl_frame = tk.Frame(inner, bg=APP_BG)
        pl_frame.pack(fill=tk.X, pady=(0, 8))
        tk.Label(pl_frame, text="📋 价目表导出设置", font=FONT_BODY_BOLD,
                 bg=APP_BG, fg=TEXT_PRIMARY).pack(anchor="w")

        self._show_trade = tk.BooleanVar()
        self._show_no_unit = tk.BooleanVar()
        self._show_empty_cats = tk.BooleanVar()
        self._align_price_list = tk.BooleanVar()
        self._price_name_width = tk.IntVar(value=12)
        self._price_value_width = tk.IntVar(value=10)
        self._cb_show_trade = self._checkbox(pl_frame, "显示价目表", self._show_trade)
        self._cb_show_no_unit = self._checkbox(pl_frame, "显示无单价项目", self._show_no_unit)
        self._cb_show_empty_cats = self._checkbox(pl_frame, "显示无工作条目的分类", self._show_empty_cats)
        self._cb_align_price_list = self._checkbox(pl_frame, "价目表列对齐", self._align_price_list)
        self._name_width_spin = self._number_row(pl_frame, "名称列宽", self._price_name_width, 4, 40)
        self._price_width_spin = self._number_row(pl_frame, "价格列宽", self._price_value_width, 4, 30)

        # ── 文字颜色 ────────────────────────────────────────────
        tc_frame = tk.Frame(inner, bg=APP_BG)
        tc_frame.pack(fill=tk.X, pady=(8, 0))
        tk.Label(tc_frame, text="🎨 文字颜色", font=FONT_BODY_BOLD,
                 bg=APP_BG, fg=TEXT_PRIMARY).pack(anchor="w")

        self._normal_color = tk.StringVar(value=TextColors().normal)
        self._muted_color = tk.StringVar(value=TextColors().muted)
        self._formula_color = tk.StringVar(value=TextColors().formula)
        self._amount_color = tk.StringVar(value=TextColors().amount)
        self._color_row(tc_frame, "普通文字", self._normal_color)
        self._color_row(tc_frame, "不重要文字", self._muted_color)
        self._color_row(tc_frame, "公式", self._formula_color)
        self._color_row(tc_frame, "金额", self._amount_color)

        # ── 其他设置 ────────────────────────────────────────────
        other_frame = tk.Frame(inner, bg=APP_BG)
        other_frame.pack(fill=tk.X, pady=(8, 0))
        tk.Label(other_frame, text="⚙ 其他设置", font=FONT_BODY_BOLD,
                 bg=APP_BG, fg=TEXT_PRIMARY).pack(anchor="w")

        self._strip_cat = tk.BooleanVar()
        self._show_date = tk.BooleanVar()
        self._show_record_time = tk.BooleanVar()
        self._show_export_time = tk.BooleanVar()
        self._append_note_to_title = tk.BooleanVar()
        self._bg_color = tk.StringVar(value=ExportDefaults().bg_color)
        self._checkbox(other_frame, "精简分类信息", self._strip_cat)
        self._checkbox(other_frame, "显示项目日期", self._show_date)
        self._checkbox(other_frame, "显示每条记录的录入时间", self._show_record_time)
        self._checkbox(other_frame, "显示导出图片时间", self._show_export_time)
        self._checkbox(other_frame, "备注追加到条目标题", self._append_note_to_title)
        self._color_row(other_frame, "背景颜色", self._bg_color)

        # ── 恢复默认 ────────────────────────────────────────────
        btn_frame = tk.Frame(inner, bg=APP_BG)
        btn_frame.pack(fill=tk.X, pady=(20, 8))
        _make_btn(btn_frame, "恢复默认设置", self._restore_defaults, "secondary").pack(side=tk.LEFT)

        canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        # ── 追踪所有变量，自动保存 ──────────────────────────────
        all_vars = [
            self._show_trade, self._show_no_unit, self._show_empty_cats,
            self._align_price_list,
            self._price_name_width, self._price_value_width,
            self._normal_color, self._muted_color,
            self._formula_color, self._amount_color,
            self._strip_cat, self._show_date,
            self._show_record_time, self._show_export_time,
            self._append_note_to_title,
            self._bg_color,
        ]
        for v in all_vars:
            v.trace_add("write", lambda *_: self._schedule_save())
        self._show_trade.trace_add("write", lambda *_: self._sync_price_list_deps())
        self._align_price_list.trace_add("write", lambda *_: self._sync_price_list_deps())

    # ── load / save ──────────────────────────────────────────────

    def _load(self):
        cfg = load_user()
        ec = ExportDefaults.from_dict(cfg.get("export_defaults", {}))
        self._show_trade.set(ec.price_list_settings.visible)
        self._show_no_unit.set(ec.price_list_settings.show_no_unit_items)
        self._show_empty_cats.set(ec.price_list_settings.show_empty_categories)
        self._align_price_list.set(ec.price_list_settings.align_columns)
        self._price_name_width.set(ec.price_list_settings.name_width)
        self._price_value_width.set(ec.price_list_settings.price_width)
        self._normal_color.set(ec.text_colors.normal)
        self._muted_color.set(ec.text_colors.muted)
        self._formula_color.set(ec.text_colors.formula)
        self._amount_color.set(ec.text_colors.amount)
        self._strip_cat.set(ec.strip_category)
        self._show_date.set(ec.show_project_date)
        self._show_record_time.set(ec.show_record_time)
        self._show_export_time.set(ec.show_export_time)
        self._append_note_to_title.set(ec.append_note_to_item_title)
        self._bg_color.set(ec.bg_color)
        self._sync_price_list_deps()

    def _save(self):
        cfg = ExportDefaults(
            price_list_settings=PriceListSettings(
                visible=self._show_trade.get(),
                show_no_unit_items=self._show_no_unit.get(),
                show_empty_categories=self._show_empty_cats.get(),
                align_columns=self._align_price_list.get(),
                name_width=max(1, self._price_name_width.get()),
                price_width=max(1, self._price_value_width.get()),
            ),
            text_colors=TextColors(
                normal=self._normal_color.get(),
                muted=self._muted_color.get(),
                formula=self._formula_color.get(),
                amount=self._amount_color.get(),
            ),
            bg_color=self._bg_color.get(),
            strip_category=self._strip_cat.get(),
            show_project_date=self._show_date.get(),
            show_record_time=self._show_record_time.get(),
            show_export_time=self._show_export_time.get(),
            append_note_to_item_title=self._append_note_to_title.get(),
        )
        user_cfg = load_user()
        user_cfg["export_defaults"] = cfg.to_dict()
        save_user(user_cfg)

    # ── restore defaults ─────────────────────────────────────────

    def _restore_defaults(self):
        app_cfg = load_app()
        d = ExportDefaults.from_dict(app_cfg.get("export_defaults", {}))
        self._show_trade.set(d.price_list_settings.visible)
        self._show_no_unit.set(d.price_list_settings.show_no_unit_items)
        self._show_empty_cats.set(d.price_list_settings.show_empty_categories)
        self._align_price_list.set(d.price_list_settings.align_columns)
        self._price_name_width.set(d.price_list_settings.name_width)
        self._price_value_width.set(d.price_list_settings.price_width)
        self._normal_color.set(d.text_colors.normal)
        self._muted_color.set(d.text_colors.muted)
        self._formula_color.set(d.text_colors.formula)
        self._amount_color.set(d.text_colors.amount)
        self._strip_cat.set(d.strip_category)
        self._show_date.set(d.show_project_date)
        self._show_record_time.set(d.show_record_time)
        self._show_export_time.set(d.show_export_time)
        self._append_note_to_title.set(d.append_note_to_item_title)
        self._bg_color.set(d.bg_color)
        self.flush_pending()

    # ── deps ─────────────────────────────────────────────────────

    def _sync_price_list_deps(self):
        if self._show_trade.get():
            self._cb_show_no_unit.config(state=tk.NORMAL)
            self._cb_show_empty_cats.config(state=tk.NORMAL)
            self._cb_align_price_list.config(state=tk.NORMAL)
            width_state = tk.NORMAL if self._align_price_list.get() else tk.DISABLED
            self._name_width_spin.config(state=width_state)
            self._price_width_spin.config(state=width_state)
        else:
            self._cb_show_no_unit.config(state=tk.DISABLED)
            self._cb_show_empty_cats.config(state=tk.DISABLED)
            self._cb_align_price_list.config(state=tk.DISABLED)
            self._name_width_spin.config(state=tk.DISABLED)
            self._price_width_spin.config(state=tk.DISABLED)
            self._show_no_unit.set(False)

    # ── widgets ──────────────────────────────────────────────────

    def _make_scrollable(self):
        canvas = tk.Canvas(self, borderwidth=0, highlightthickness=0, bg=APP_BG)
        scrollbar = ttk.Scrollbar(self, orient=tk.VERTICAL, command=canvas.yview)
        canvas.configure(yscrollcommand=scrollbar.set)
        inner = tk.Frame(canvas, bg=APP_BG)
        inner.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        win_id = canvas.create_window((0, 0), window=inner, anchor="nw")
        canvas.bind("<Configure>", lambda e, wid=win_id: canvas.itemconfig(wid, width=e.width))

        def _on_mousewheel(e):
            canvas.yview_scroll(int(-1 * (e.delta / 120)), "units")

        def _bind_wheel(widget):
            widget.bind("<MouseWheel>", _on_mousewheel)
            for child in widget.winfo_children():
                _bind_wheel(child)

        canvas.bind("<MouseWheel>", _on_mousewheel)
        _bind_wheel(inner)
        return canvas, scrollbar, inner

    def _checkbox(self, parent, text, var):
        cb = tk.Checkbutton(parent, text=text, variable=var, font=FONT_BODY,
                            bg=APP_BG, activebackground=APP_BG, anchor="w")
        cb.pack(fill=tk.X, pady=2)
        return cb

    def _number_row(self, parent, label, var, from_, to):
        row_f = tk.Frame(parent, bg=APP_BG)
        row_f.pack(fill=tk.X, pady=3)
        tk.Label(row_f, text=label, font=FONT_BODY, bg=APP_BG, fg=TEXT_PRIMARY,
                 width=10, anchor="w").pack(side=tk.LEFT)
        spin = ttk.Spinbox(row_f, from_=from_, to=to, textvariable=var, width=6)
        spin.pack(side=tk.LEFT)
        return spin

    def _color_row(self, parent, label, var):
        row_f = tk.Frame(parent, bg=APP_BG)
        row_f.pack(fill=tk.X, pady=3)
        tk.Label(row_f, text=label, font=FONT_BODY, bg=APP_BG, fg=TEXT_PRIMARY,
                 width=10, anchor="w").pack(side=tk.LEFT)

        entry = ttk.Entry(row_f, textvariable=var, font=FONT_SMALL, width=12)
        entry.pack(side=tk.LEFT, padx=(0, 6))

        swatch = tk.Label(row_f, text="  ●  ", font=FONT_BODY, bg=var.get(),
                          fg="white" if self._is_dark(var.get()) else "black",
                          cursor="hand2", relief="groove", bd=1)
        swatch.pack(side=tk.LEFT, padx=(0, 6))

        def pick():
            code, color = colorchooser.askcolor(
                title="选择颜色",
                parent=self.winfo_toplevel(),
                initialcolor=var.get(),
            )
            if color:
                var.set(color)

        def update_swatch(*_):
            c = var.get()
            try:
                swatch.config(bg=c, fg="white" if self._is_dark(c) else "black")
            except tk.TclError:
                pass

        var.trace_add("write", update_swatch)
        _make_btn(row_f, "选择", pick, "secondary").pack(side=tk.LEFT)

    @staticmethod
    def _is_dark(hex_color):
        try:
            h = hex_color.lstrip("#")
            if len(h) != 6:
                return False
            r, g, b = int(h[:2], 16), int(h[2:4], 16), int(h[4:6], 16)
            return (r * 0.299 + g * 0.587 + b * 0.114) < 128
        except Exception:
            return False
