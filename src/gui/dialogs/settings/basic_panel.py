"""基础设置面板。"""

import tkinter as tk
from tkinter import ttk, colorchooser

from .base import BaseSettingsPanel, register_section
from ...theme import APP_BG, TEXT_PRIMARY, TEXT_SECONDARY, FONT_BODY, FONT_SMALL, FONT_BODY_BOLD
from ...widgets import _make_btn
from ....config_loader import load_app, save_app
from ....symbol_mapping import DEFAULT_SYMBOL_MAPPING, normalize_symbol_mapping


@register_section
class BasicSettingsPanel(BaseSettingsPanel):
    section_id = "basic"
    section_title = "基础设置"
    section_icon = "⚙"
    section_order = 0

    def _build(self):
        tk.Label(self, text=f"{self.section_icon} 基础设置", font=FONT_BODY_BOLD,
                 bg=APP_BG, fg=TEXT_PRIMARY).pack(anchor="w")
        tk.Label(self, text="这些设置会写入 app_config.json，作为应用级默认值。",
                 font=FONT_SMALL, bg=APP_BG, fg=TEXT_SECONDARY).pack(anchor="w", pady=(2, 12))

        row = tk.Frame(self, bg=APP_BG)
        row.pack(fill=tk.X, pady=3)
        tk.Label(row, text="备份数量", font=FONT_BODY, bg=APP_BG, fg=TEXT_PRIMARY,
                 width=10, anchor="w").pack(side=tk.LEFT)
        self._backup_count = tk.IntVar(value=10)
        self._backup_spin = ttk.Spinbox(row, from_=1, to=100, textvariable=self._backup_count, width=8)
        self._backup_spin.pack(side=tk.LEFT)
        tk.Label(row, text="每个项目最多保留的备份文件数", font=FONT_SMALL,
                 bg=APP_BG, fg=TEXT_SECONDARY).pack(side=tk.LEFT, padx=(8, 0))

        self._backup_count.trace_add("write", lambda *_: self._schedule_save())

        tk.Frame(self, bg="#e2e8f0", height=1).pack(fill=tk.X, pady=12)
        tk.Label(self, text="账单管理设置", font=FONT_BODY_BOLD,
                 bg=APP_BG, fg=TEXT_PRIMARY).pack(anchor="w")
        tk.Label(self, text="颜色值使用 #RRGGBB 格式；选中颜色优先于已审核行颜色。",
                 font=FONT_SMALL, bg=APP_BG, fg=TEXT_SECONDARY).pack(anchor="w", pady=(2, 8))
        self._selection_color = tk.StringVar(value="#90cdf4")
        self._reviewed_color = tk.StringVar(value="#e6fffa")
        self._color_row("选中行颜色", self._selection_color)
        self._color_row("已审核行颜色", self._reviewed_color)
        self._selection_color.trace_add("write", lambda *_: self._schedule_save())
        self._reviewed_color.trace_add("write", lambda *_: self._schedule_save())

        tk.Frame(self, bg="#e2e8f0", height=1).pack(fill=tk.X, pady=12)
        tk.Label(self, text="符号映射", font=FONT_BODY_BOLD,
                 bg=APP_BG, fg=TEXT_PRIMARY).pack(anchor="w")
        tk.Label(self, text="符号映射从 app_config.json 读取，仅在此展示；如需修改请编辑配置文件。",
                 font=FONT_SMALL, bg=APP_BG, fg=TEXT_SECONDARY).pack(anchor="w", pady=(2, 8))
        self._symbol_display = tk.Text(self, height=11, font=FONT_SMALL, width=72, wrap="word",
                                       bg="white", fg=TEXT_PRIMARY, relief="solid", bd=1)
        self._symbol_display.pack(fill=tk.X)
        self._symbol_display.config(state=tk.DISABLED)

    def _color_row(self, label: str, var: tk.StringVar) -> None:
        row = tk.Frame(self, bg=APP_BG)
        row.pack(fill=tk.X, pady=3)
        tk.Label(row, text=label, font=FONT_BODY, bg=APP_BG, fg=TEXT_PRIMARY,
                 width=12, anchor="w").pack(side=tk.LEFT)
        entry = ttk.Entry(row, textvariable=var, font=FONT_SMALL, width=12)
        entry.pack(side=tk.LEFT, padx=(0, 6))
        swatch = tk.Label(row, text="  ●  ", font=FONT_BODY, bg=var.get(),
                          fg="white" if self._is_dark(var.get()) else "black",
                          cursor="hand2", relief="groove", bd=1)
        swatch.pack(side=tk.LEFT, padx=(0, 6))

        def pick():
            _code, color = colorchooser.askcolor(
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
        _make_btn(row, "选择", pick, "secondary").pack(side=tk.LEFT)

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

    def _load(self):
        cfg = load_app()
        self._backup_count.set(max(1, int(cfg.get("backup_count", 10))))
        self._selection_color.set(cfg.get("selection_highlight_color", "#90cdf4"))
        self._reviewed_color.set(cfg.get("bill_reviewed_row_color", "#e6fffa"))
        mapping = normalize_symbol_mapping(cfg.get("symbol_mapping") or DEFAULT_SYMBOL_MAPPING)
        lines = []
        lines.append("运算符：")
        for canonical in ("+", "-", "*", "/"):
            item = mapping["operators"][canonical]
            aliases = " ".join(item.get("aliases", [])) or "无"
            lines.append(
                f"  {canonical}  {item.get('label', '')}  别名：{aliases}  语音：{item.get('voice_key', canonical)}"
            )
        lines.append("")
        lines.append("括号对：")
        for pair in mapping.get("bracket_pairs", []):
            lines.append(
                f"  {pair['left']} {pair['right']}  {pair['left_label']} / {pair['right_label']}  "
                f"语音：{pair.get('voice_left_key', '(')} / {pair.get('voice_right_key', ')')}"
            )
        self._symbol_display.config(state=tk.NORMAL)
        self._symbol_display.delete("1.0", tk.END)
        self._symbol_display.insert("1.0", "\n".join(lines))
        self._symbol_display.config(state=tk.DISABLED)

    def _save(self):
        cfg = load_app()
        cfg["backup_count"] = max(1, int(self._backup_count.get()))
        cfg["selection_highlight_color"] = self._selection_color.get().strip() or "#90cdf4"
        cfg["bill_reviewed_row_color"] = self._reviewed_color.get().strip() or "#e6fffa"
        save_app(cfg)
