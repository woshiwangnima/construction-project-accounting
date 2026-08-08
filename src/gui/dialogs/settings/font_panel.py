"""Font settings panel: global default_font_size + per-role font customization."""

_PREVIEW_TEXT = "预览 Ab 123"

import tkinter as tk
from tkinter import ttk, colorchooser, font as tkfont

from .base import (
    BaseSettingsPanel,
    bind_responsive_wrap,
    normalize_hex_color,
    register_section,
)
from ...theme import APP_BG, ROW_STRIPE, SEPARATOR, TEXT_PRIMARY, TEXT_SECONDARY, FONT_BODY, FONT_SMALL, FONT_BODY_BOLD
from ...widgets import ScrollableFrame, _make_btn
from ...font_manager import (
    font_manager, ROLE_KEYS, ROLE_DISPLAY_NAMES, ROLE_GROUPS,
    _ROLE_DEFAULTS, _ROLE_SIZE_MULTIPLIERS, _DEFAULT_FONT_SIZE,
)
from ....config_loader import load_app, load_user


_FONT_SIZE_SAVE_DEBOUNCE_MS = 250


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
        self._font_size_save_after_id: str | None = None

        # ── Top section: default_font_size ──────────────────────────────────
        self._build_header(inner)

        # ── Role rows grouped by category ───────────────────────────────────
        for group_name, role_keys in ROLE_GROUPS:
            tk.Frame(inner, bg=SEPARATOR, height=1).pack(fill=tk.X, pady=12)
            tk.Label(inner, text=group_name, font=FONT_BODY_BOLD,
                     bg=APP_BG, fg=TEXT_PRIMARY).pack(anchor="w")
            for role in role_keys:
                if role not in ROLE_KEYS:
                    continue
                self._build_role_row(inner, role)

        # ── Bottom: reset button ────────────────────────────────────────────
        tk.Frame(inner, bg=SEPARATOR, height=1).pack(fill=tk.X, pady=12)
        btn_frame = tk.Frame(inner, bg=APP_BG)
        btn_frame.pack(fill=tk.X, pady=(4, 8))
        _make_btn(btn_frame, "恢复默认", self._on_reset, "secondary").pack(side=tk.LEFT)

    def _build_header(self, parent):
        """Build the top section with slider + inline preview."""
        tk.Label(parent, text=f"{self.section_icon} 字体设置", font=FONT_BODY_BOLD,
                 bg=APP_BG, fg=TEXT_PRIMARY).pack(anchor="w")
        hint = tk.Label(parent, text="全局基础字号决定所有角色的默认大小。",
                        font=FONT_SMALL, bg=APP_BG, fg=TEXT_SECONDARY,
                        justify="left")
        hint.pack(fill=tk.X, anchor="w", pady=(2, 8))
        bind_responsive_wrap(hint, parent, padding=4)

        scale_frame = tk.Frame(parent, bg=APP_BG)
        scale_frame.pack(fill=tk.X, pady=(0, 4))

        self._size_scale_var = tk.IntVar(value=_DEFAULT_FONT_SIZE)
        self._size_scale = tk.Scale(
            scale_frame, from_=10, to=30, orient=tk.HORIZONTAL,
            variable=self._size_scale_var,
            bg=APP_BG, fg=TEXT_PRIMARY, troughcolor=SEPARATOR,
            highlightthickness=0, sliderrelief="flat", length=300,
            showvalue=False,
        )
        self._size_scale.pack(side=tk.LEFT, fill=tk.X, expand=True)
        self._size_scale.config(command=self._on_scale_change)

        self._scale_value_lbl = tk.Label(scale_frame, text=f"当前值: {_DEFAULT_FONT_SIZE}",
                                         font=FONT_BODY, bg=APP_BG, fg=TEXT_PRIMARY,
                                         width=10, anchor="w")
        self._scale_value_lbl.pack(side=tk.LEFT, padx=(8, 0))

        self._preview_font = tkfont.Font(family="Microsoft YaHei UI", size=_DEFAULT_FONT_SIZE)
        preview_frame = tk.Frame(parent, bg=APP_BG)
        preview_frame.pack(fill=tk.X, pady=(4, 0))
        self._preview_lbl = tk.Label(preview_frame, text=_PREVIEW_TEXT, bg="white", fg="black",
                                     font=self._preview_font, padx=8, pady=4,
                                     relief="solid", bd=1)
        self._preview_lbl.pack(anchor="w")

        tk.Frame(parent, bg=APP_BG, height=4).pack()

    def _build_role_row(self, parent, role: str):
        """Build a single role configuration row."""
        defaults = _ROLE_DEFAULTS[role]
        rv: dict = {}

        # Role label
        role_label = tk.Label(parent, text=f"  {ROLE_DISPLAY_NAMES[role]}", font=FONT_BODY,
                              bg=APP_BG, fg=TEXT_SECONDARY, justify="left")
        role_label.pack(fill=tk.X, anchor="w", pady=(8, 2))
        bind_responsive_wrap(role_label, parent, padding=16)

        family_row = tk.Frame(parent, bg=APP_BG)
        family_row.pack(fill=tk.X, padx=8)

        # Font family combobox
        rv["family"] = tk.StringVar(value=defaults["family"])
        cb = ttk.Combobox(family_row, textvariable=rv["family"], values=self._families,
                          width=18, state="readonly")
        cb.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 4))

        # Size spinbox
        rv["size"] = tk.IntVar(value=defaults["size"])
        ttk.Spinbox(family_row, textvariable=rv["size"], from_=8, to=72, width=4).pack(
            side=tk.LEFT, padx=(0, 4))

        style_row = tk.Frame(parent, bg=APP_BG)
        style_row.pack(fill=tk.X, padx=8, pady=(2, 0))

        # Bold / Italic / Underline / Overstrike checkboxes
        for key, label in [("bold", "B"), ("italic", "I"), ("underline", "U"), ("overstrike", "S")]:
            rv[key] = tk.BooleanVar(value=defaults[key])
            cb_btn = tk.Checkbutton(
                style_row, text=label, variable=rv[key],
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
        color_entry = ttk.Entry(style_row, textvariable=rv["color"], width=9, font=FONT_SMALL)
        color_entry.pack(side=tk.LEFT, padx=(6, 2))

        swatch = tk.Label(style_row, text=" \u25cf ", bg=defaults["color"],
                          fg="white" if self._is_dark(defaults["color"]) else "black",
                          cursor="hand2", relief="flat", bd=0)
        swatch.pack(side=tk.LEFT, padx=(0, 4))

        def pick_color(v=rv["color"], sw=swatch):
            _code, color = colorchooser.askcolor(
                title="选择颜色", parent=self.winfo_toplevel(),
                initialcolor=normalize_hex_color(v.get(), defaults["color"]),
            )
            if color:
                v.set(color)

        def update_swatch(*_):
            c = normalize_hex_color(rv["color"].get(), "")
            try:
                swatch.config(bg=c or ROW_STRIPE, fg="white" if c and self._is_dark(c) else "black")
            except tk.TclError:
                pass

        rv["color"].trace_add("write", update_swatch)
        _make_btn(style_row, "选择", pick_color, "secondary").pack(side=tk.LEFT, padx=(0, 8))

        # Preview label — uses a dedicated Font object for underline/overstrike support
        preview_font = tkfont.Font(
            family=defaults["family"], size=defaults["size"],
            weight="bold" if defaults["bold"] else "normal",
            slant="italic" if defaults["italic"] else "roman",
            underline=1 if defaults["underline"] else 0,
            overstrike=1 if defaults["overstrike"] else 0,
        )
        preview_row = tk.Frame(parent, bg=APP_BG)
        preview_row.pack(fill=tk.X, padx=8)
        preview = tk.Label(preview_row, text="预览 Abc 123", bg=APP_BG,
                           font=preview_font, fg=defaults["color"])
        preview.pack(anchor="w", padx=(4, 0))
        self._previews[role] = preview
        self._preview_fonts[role] = preview_font

        self._vars[role] = rv

        # Traces for auto-save + preview update
        for var in rv.values():
            var.trace_add("write", lambda *_: self._on_var_change(role))

    # ── Event handlers ─────────────────────────────────────────────────────

    def _on_scale_change(self, value):
        """Scale dragged — apply immediately."""
        size = int(float(value))
        self._size_scale_var.set(size)
        self._on_size_change()

    def _on_size_change(self):
        """Called when default_font_size changes via scale."""
        size = self._size_scale_var.get()
        self._scale_value_lbl.config(text=f"当前值: {size}")
        self._preview_font.configure(size=size)
        self._schedule_font_size_save()
        self._update_all_previews()

    def _schedule_font_size_save(self):
        if self._loading or self._closed:
            return
        if self._font_size_save_after_id is not None:
            try:
                self.after_cancel(self._font_size_save_after_id)
            except tk.TclError:
                pass
        try:
            self._font_size_save_after_id = self.after(
                _FONT_SIZE_SAVE_DEBOUNCE_MS, self._save_font_size_now
            )
        except tk.TclError:
            self._font_size_save_after_id = None

    def _save_font_size_now(self):
        self._font_size_save_after_id = None
        if self._loading or self._closed:
            return
        font_manager.save_default_font_size(self._size_scale_var.get())

    def _cancel_font_size_save(self):
        if self._font_size_save_after_id is not None:
            try:
                self.after_cancel(self._font_size_save_after_id)
            except tk.TclError:
                pass
            self._font_size_save_after_id = None

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
        self._size_scale_var.set(dfs)
        self._scale_value_lbl.config(text=f"当前值: {dfs}")
        self._preview_font.configure(size=dfs)

        # Load per-role font_settings from user_config
        cfg = load_user().get("font_settings", {})
        for role in ROLE_KEYS:
            if role not in self._vars:
                continue
            rv = self._vars[role]
            user = cfg.get(role, {})
            defaults = _ROLE_DEFAULTS[role]
            family = user.get("family", defaults["family"])
            rv["family"].set(family if family in self._families else defaults["family"])
            try:
                role_size = max(8, min(72, int(user.get("size", defaults["size"]))))
            except (TypeError, ValueError):
                role_size = defaults["size"]
            rv["size"].set(role_size)
            rv["bold"].set(bool(user.get("bold", defaults["bold"])))
            rv["italic"].set(bool(user.get("italic", defaults["italic"])))
            rv["underline"].set(bool(user.get("underline", defaults["underline"])))
            rv["overstrike"].set(bool(user.get("overstrike", defaults["overstrike"])))
            rv["color"].set(normalize_hex_color(user.get("color"), defaults["color"]))
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
                    "color": normalize_hex_color(
                        rv["color"].get(), _ROLE_DEFAULTS[role]["color"]
                    ),
                }
            except (tk.TclError, ValueError):
                settings[role] = _ROLE_DEFAULTS[role].copy()
        font_manager.save_settings(settings)

    def _on_reset(self):
        """Reset both default_font_size and all per-role settings."""
        self._cancel_font_size_save()
        self.cancel_pending()
        font_manager.reset_all()
        font_manager.save_default_font_size(_DEFAULT_FONT_SIZE)
        self._loading = True
        try:
            self._load()
        finally:
            self._loading = False

    def flush_pending(self) -> None:
        """Flush both the global size debounce and role settings debounce."""
        if self._font_size_save_after_id is not None:
            self._cancel_font_size_save()
            self._save_font_size_now()
        super().flush_pending()

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
