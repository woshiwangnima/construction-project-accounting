"""Font settings panel: global default_font_size + per-role font customization."""

import tkinter as tk
from tkinter import ttk, colorchooser, font as tkfont

from .base import BaseSettingsPanel, register_section
from ...theme import APP_BG, TEXT_PRIMARY, TEXT_SECONDARY, FONT_BODY, FONT_SMALL, FONT_BODY_BOLD
from ...widgets import ScrollableFrame, _make_btn
from ...font_manager import (
    font_manager, ROLE_KEYS, ROLE_DISPLAY_NAMES, ROLE_GROUPS,
    _ROLE_DEFAULTS, _ROLE_SIZE_MULTIPLIERS, _DEFAULT_FONT_SIZE,
)
from ....config_loader import load_app, save_app, load_user, save_user
from ....logger import logger


@register_section
class FontSettingsPanel(BaseSettingsPanel):
    section_id = "font"
    section_title = "字体设置"
    section_icon = "\U0001f524"  # 🔤
    section_order = 5

    # ── Build ──────────────────────────────────────────────────────────────

    def _build(self):
        sf = ScrollableFrame(self, auto_hide_ms=None, bg=APP_BG)
        sf.pack(fill=tk.BOTH, expand=True)
        inner = sf.inner

        self._families = sorted(tkfont.families())
        self._vars: dict[str, dict] = {}
        self._previews: dict[str, tk.Label] = {}
        self._preview_fonts: dict[str, tkfont.Font] = {}

        # ── Top section: default_font_size ──────────────────────────────────
        self._build_header(inner)

        # ── Role rows grouped by category ───────────────────────────────────
        for group_name, role_keys in ROLE_GROUPS:
            tk.Frame(inner, bg="#e2e8f0", height=1).pack(fill=tk.X, pady=12)
            tk.Label(inner, text=group_name, font=FONT_BODY_BOLD,
                     bg=APP_BG, fg=TEXT_PRIMARY).pack(anchor="w")
            for role in role_keys:
                if role not in ROLE_KEYS:
                    continue
                self._build_role_row(inner, role)

        # ── Bottom: reset button ────────────────────────────────────────────
        tk.Frame(inner, bg="#e2e8f0", height=1).pack(fill=tk.X, pady=12)
        btn_frame = tk.Frame(inner, bg=APP_BG)
        btn_frame.pack(fill=tk.X, pady=(4, 8))
        _make_btn(btn_frame, "恢复默认", self._on_reset, "secondary").pack(side=tk.LEFT)

    def _build_header(self, parent):
        """Build the top section with title, radio buttons, and scale slider."""
        tk.Label(parent, text=f"{self.section_icon} 字体设置", font=FONT_BODY_BOLD,
                 bg=APP_BG, fg=TEXT_PRIMARY).pack(anchor="w")
        tk.Label(parent, text="全局基础字号决定所有角色的默认大小。",
                 font=FONT_SMALL, bg=APP_BG, fg=TEXT_SECONDARY).pack(anchor="w", pady=(2, 8))

        # Radio buttons row
        radio_frame = tk.Frame(parent, bg=APP_BG)
        radio_frame.pack(anchor="w", pady=(0, 4))

        self._size_radio = tk.IntVar(value=_DEFAULT_FONT_SIZE)
        for label, val in [("小号 (12)", 12), ("中号 (14)", 14), ("大号 (16)", 16)]:
            tk.Radiobutton(
                radio_frame, text=label, variable=self._size_radio, value=val,
                command=self._on_radio_change,
                bg=APP_BG, fg=TEXT_PRIMARY, activebackground=APP_BG,
                selectcolor=APP_BG, font=FONT_BODY,
            ).pack(side=tk.LEFT, padx=(0, 12))

        # Scale / slider row
        scale_frame = tk.Frame(parent, bg=APP_BG)
        scale_frame.pack(fill=tk.X, pady=(0, 4))

        self._size_scale = tk.IntVar(value=_DEFAULT_FONT_SIZE)
        self._scale_widget = ttk.Scale(
            scale_frame, from_=10, to=30, variable=self._size_scale,
            command=self._on_scale_change,
        )
        self._scale_widget.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 8))

        self._scale_value_label = tk.Label(
            scale_frame, text=f"当前值: {_DEFAULT_FONT_SIZE}",
            font=FONT_BODY, bg=APP_BG, fg=TEXT_PRIMARY, width=12, anchor="w",
        )
        self._scale_value_label.pack(side=tk.LEFT)

        tk.Frame(parent, bg=APP_BG, height=4).pack()

    def _build_role_row(self, parent, role: str):
        """Build a single role configuration row."""
        defaults = _ROLE_DEFAULTS[role]
        rv: dict = {}

        # Role label
        tk.Label(parent, text=f"  {ROLE_DISPLAY_NAMES[role]}", font=FONT_BODY,
                 bg=APP_BG, fg=TEXT_SECONDARY).pack(anchor="w", pady=(8, 2))

        row = tk.Frame(parent, bg=APP_BG)
        row.pack(fill=tk.X, padx=8)

        # Font family combobox
        rv["family"] = tk.StringVar(value=defaults["family"])
        cb = ttk.Combobox(row, textvariable=rv["family"], values=self._families,
                          width=22, state="readonly")
        cb.pack(side=tk.LEFT, padx=(0, 4))

        # Size spinbox
        rv["size"] = tk.IntVar(value=defaults["size"])
        ttk.Spinbox(row, textvariable=rv["size"], from_=8, to=72, width=4).pack(
            side=tk.LEFT, padx=(0, 4))

        # Bold / Italic / Underline / Overstrike checkboxes
        for key, label in [("bold", "B"), ("italic", "I"), ("underline", "U"), ("overstrike", "S")]:
            rv[key] = tk.BooleanVar(value=defaults[key])
            cb_btn = tk.Checkbutton(
                row, text=label, variable=rv[key],
                bg=APP_BG, fg=TEXT_PRIMARY, activebackground=APP_BG,
                selectcolor=APP_BG, relief="flat", bd=1,
                font=("Microsoft YaHei UI", 10,
                      "bold" if key == "bold" else
                      "italic" if key == "italic" else
                      "overstrike" if key == "overstrike" else "normal"),
            )
            cb_btn.pack(side=tk.LEFT, padx=1)

        # Color entry + swatch + picker button
        rv["color"] = tk.StringVar(value=defaults["color"])
        color_entry = ttk.Entry(row, textvariable=rv["color"], width=9, font=FONT_SMALL)
        color_entry.pack(side=tk.LEFT, padx=(6, 2))

        swatch = tk.Label(row, text=" \u25cf ", bg=defaults["color"],
                          fg="white" if self._is_dark(defaults["color"]) else "black",
                          cursor="hand2", relief="groove", bd=1)
        swatch.pack(side=tk.LEFT, padx=(0, 4))

        def pick_color(v=rv["color"], sw=swatch):
            _code, color = colorchooser.askcolor(
                title="选择颜色", parent=self.winfo_toplevel(),
                initialcolor=v.get(),
            )
            if color:
                v.set(color)

        def update_swatch(*_):
            c = rv["color"].get()
            try:
                swatch.config(bg=c, fg="white" if self._is_dark(c) else "black")
            except tk.TclError:
                pass

        rv["color"].trace_add("write", update_swatch)
        _make_btn(row, "选择", pick_color, "secondary").pack(side=tk.LEFT, padx=(0, 8))

        # Preview label — uses a dedicated Font object for underline/overstrike support
        preview_font = tkfont.Font(
            family=defaults["family"], size=defaults["size"],
            weight="bold" if defaults["bold"] else "normal",
            slant="italic" if defaults["italic"] else "roman",
            underline=1 if defaults["underline"] else 0,
            overstrike=1 if defaults["overstrike"] else 0,
        )
        preview = tk.Label(row, text="预览 Abc 123", bg=APP_BG,
                           font=preview_font, fg=defaults["color"])
        preview.pack(side=tk.LEFT, padx=(4, 0))
        self._previews[role] = preview
        self._preview_fonts[role] = preview_font

        self._vars[role] = rv

        # Traces for auto-save + preview update
        for var in rv.values():
            var.trace_add("write", lambda *_: self._on_var_change(role))

    # ── Event handlers ─────────────────────────────────────────────────────

    def _on_radio_change(self):
        """Radio button clicked — sync scale and apply."""
        size = self._size_radio.get()
        self._size_scale.set(size)
        self._on_size_change()

    def _on_scale_change(self, value):
        """Scale dragged — sync radio if value matches a preset, then apply."""
        size = int(float(value))
        self._size_scale.set(size)
        if size in (12, 14, 16):
            self._size_radio.set(size)
        self._on_size_change()

    def _on_size_change(self):
        """Called when default_font_size changes (radio or scale)."""
        size = self._size_scale.get()
        # Sync radio if value matches a preset
        if size in (12, 14, 16):
            self._size_radio.set(size)
        # Update the value label
        self._scale_value_label.config(text=f"当前值: {size}")
        # Save immediately (not debounced) since this affects all roles
        if not self._loading:
            font_manager.save_default_font_size(size)
        # Update all preview labels with new computed sizes
        self._update_all_previews()

    def _on_var_change(self, role: str):
        """Called when any variable for a role changes — update preview + schedule save."""
        self._update_preview(role)
        self._schedule_save()

    # ── Preview updates ────────────────────────────────────────────────────

    def _update_preview(self, role: str):
        """Update a single role's preview font and color."""
        rv = self._vars[role]
        preview_font = self._preview_fonts.get(role)
        preview = self._previews.get(role)
        if not preview_font or not preview or not preview.winfo_exists():
            return
        try:
            preview_font.configure(
                family=rv["family"].get(),
                size=int(rv["size"].get()),
                weight="bold" if rv["bold"].get() else "normal",
                slant="italic" if rv["italic"].get() else "roman",
                underline=1 if rv["underline"].get() else 0,
                overstrike=1 if rv["overstrike"].get() else 0,
            )
            preview.config(fg=rv["color"].get())
        except (tk.TclError, ValueError):
            pass

    def _update_all_previews(self):
        """Refresh every role's preview label."""
        for role in self._vars:
            self._update_preview(role)

    # ── Load / Save ────────────────────────────────────────────────────────

    def _load(self):
        # Load default_font_size from app_config
        try:
            app_cfg = load_app()
            dfs = int(app_cfg.get("default_font_size", _DEFAULT_FONT_SIZE))
        except Exception:
            dfs = _DEFAULT_FONT_SIZE
        self._size_radio.set(dfs)
        self._size_scale.set(dfs)
        self._scale_value_label.config(text=f"当前值: {dfs}")

        # Load per-role font_settings from user_config
        cfg = load_user().get("font_settings", {})
        for role in ROLE_KEYS:
            if role not in self._vars:
                continue
            rv = self._vars[role]
            user = cfg.get(role, {})
            defaults = _ROLE_DEFAULTS[role]
            rv["family"].set(user.get("family", defaults["family"]))
            rv["size"].set(int(user.get("size", defaults["size"])))
            rv["bold"].set(bool(user.get("bold", defaults["bold"])))
            rv["italic"].set(bool(user.get("italic", defaults["italic"])))
            rv["underline"].set(bool(user.get("underline", defaults["underline"])))
            rv["overstrike"].set(bool(user.get("overstrike", defaults["overstrike"])))
            rv["color"].set(user.get("color", defaults["color"]))
            self._update_preview(role)

    def _save(self):
        """Save per-role font_settings to user_config.

        default_font_size is saved separately via font_manager.save_default_font_size()
        in _on_size_change(), not here.
        """
        settings = {}
        for role in ROLE_KEYS:
            if role not in self._vars:
                continue
            rv = self._vars[role]
            try:
                settings[role] = {
                    "family": rv["family"].get(),
                    "size": int(rv["size"].get()),
                    "bold": rv["bold"].get(),
                    "italic": rv["italic"].get(),
                    "underline": rv["underline"].get(),
                    "overstrike": rv["overstrike"].get(),
                    "color": rv["color"].get().strip() or _ROLE_DEFAULTS[role]["color"],
                }
            except (tk.TclError, ValueError):
                settings[role] = _ROLE_DEFAULTS[role].copy()
        font_manager.save_settings(settings)

    def _on_reset(self):
        """Reset both default_font_size and all per-role settings."""
        font_manager.reset_all()
        font_manager.save_default_font_size(_DEFAULT_FONT_SIZE)
        # Reload UI from defaults
        self._loading = True
        try:
            self._load()
        finally:
            self._loading = False

    # ── Utilities ──────────────────────────────────────────────────────────

    @staticmethod
    def _is_dark(hex_color):
        """Return True if the color is dark (needs light foreground text)."""
        try:
            h = hex_color.lstrip("#")
            if len(h) != 6:
                return False
            r, g, b = int(h[:2], 16), int(h[2:4], 16), int(h[4:6], 16)
            return (r * 0.299 + g * 0.587 + b * 0.114) < 128
        except Exception:
            return False
