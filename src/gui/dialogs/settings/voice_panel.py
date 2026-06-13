"""🎙 语音播报设置面板。

存储位置：app_config.json::voice
写入后会调用 VoiceEngine.reload() 让引擎立即应用新值。
"""

import tkinter as tk

from .base import BaseSettingsPanel, register_section
from ...theme import APP_BG, TEXT_PRIMARY, TEXT_SECONDARY, FONT_BODY, FONT_SMALL, FONT_BODY_BOLD
from ...widgets import ScrollableFrame, _make_btn
from ....config_loader import load_app, save_app
from ....voice import get_voice


@register_section
class VoiceSettingsPanel(BaseSettingsPanel):
    section_id = "voice"
    section_title = "语音播报"
    section_icon = "🎙"
    section_order = 10

    VOL_MIN, VOL_MAX = 0, 100
    RATE_MIN, RATE_MAX = 50, 400

    def _build(self):
        sf = ScrollableFrame(self, auto_hide_ms=None, bg=APP_BG)
        sf.pack(fill=tk.BOTH, expand=True)
        inner = sf.inner

        tk.Label(inner, text=f"{self.section_icon} 语音播报", font=FONT_BODY_BOLD,
                 bg=APP_BG, fg=TEXT_PRIMARY).pack(anchor="w", pady=(0, 12))
        # 启用开关
        self._enabled_var = tk.BooleanVar()
        tk.Checkbutton(
            inner,
            text="启用语音播报（按键音 + 公式朗读）",
            variable=self._enabled_var,
            font=FONT_BODY,
            bg=APP_BG,
            activebackground=APP_BG,
            anchor="w",
            command=self._on_enabled_change,
        ).pack(anchor="w", pady=(0, 12), fill=tk.X)

        # 音量
        self._build_section(
            inner, "🔊 音量",
            "影响按键音（WAV）和公式朗读音量",
        )
        self._vol_scale, self._vol_value_lbl = self._make_scale_row(
            inner, self.VOL_MIN, self.VOL_MAX, suffix="",
        )
        self._vol_scale.config(command=self._on_vol_change)

        # 语速
        self._build_section(
            inner, "🗣 公式朗读语速",
            "仅影响 🔊 朗读按钮；不影响 0–9、运算符等按键音速度",
            wrap=True,
        )
        self._rate_scale, self._rate_value_lbl = self._make_scale_row(
            inner, self.RATE_MIN, self.RATE_MAX, suffix=" 词/分",
        )
        self._rate_scale.config(command=self._on_rate_change)

        # 试播
        try_frame = tk.Frame(inner, bg=APP_BG)
        try_frame.pack(fill=tk.X, pady=(20, 0))
        _make_btn(try_frame, "▶ 试播示例", self._on_preview, "secondary").pack(side=tk.LEFT)
        self._preview_text = tk.StringVar()
        tk.Label(inner, textvariable=self._preview_text, font=FONT_SMALL,
                 bg=APP_BG, fg=TEXT_SECONDARY, justify="left",
                 wraplength=520).pack(anchor="w", pady=(8, 0))

    def _build_section(self, parent, title, hint, wrap=False):
        header = tk.Frame(parent, bg=APP_BG)
        header.pack(fill=tk.X, pady=(12, 2), anchor="w")
        tk.Label(header, text=title, font=FONT_BODY_BOLD,
                 bg=APP_BG, fg=TEXT_PRIMARY).pack(anchor="w")
        lbl = tk.Label(header, text=hint, font=FONT_SMALL,
                       bg=APP_BG, fg=TEXT_SECONDARY, justify="left")
        if wrap:
            lbl.config(wraplength=380)
        lbl.pack(anchor="w")

    def _make_scale_row(self, container, frm, to, suffix=""):
        row = tk.Frame(container, bg=APP_BG)
        row.pack(fill=tk.X, pady=(2, 0))
        scale = tk.Scale(
            row, from_=frm, to=to, orient=tk.HORIZONTAL,
            bg=APP_BG, fg=TEXT_PRIMARY, troughcolor="#e2e8f0",
            highlightthickness=0, sliderrelief="raised", length=300,
            showvalue=False,
        )
        scale.pack(side=tk.LEFT, fill=tk.X, expand=True)
        value_lbl = tk.Label(row, text=str(frm) + suffix, font=FONT_BODY,
                             bg=APP_BG, fg=TEXT_PRIMARY, width=10, anchor="w")
        value_lbl.pack(side=tk.LEFT, padx=(8, 0))
        return scale, value_lbl

    def _load(self):
        cfg = load_app()
        voice = cfg.get("voice", {}) or {}
        self._enabled_var.set(bool(voice.get("enabled", True)))
        self._vol_scale.set(int(voice.get("volume", 80)))
        self._rate_scale.set(int(voice.get("tts_rate", 150)))
        self._preview_text.set(str(voice.get("preview_text") or "2 加 3 等于 5"))
        self._refresh_labels()

    def _save(self):
        cfg = load_app()
        voice = cfg.setdefault("voice", {})
        voice["enabled"] = bool(self._enabled_var.get())
        voice["volume"] = int(self._vol_scale.get())
        voice["tts_rate"] = int(self._rate_scale.get())
        voice.setdefault("preview_text", self._preview_text.get())
        save_app(cfg)
        get_voice().reload()

    def _on_enabled_change(self):
        self._schedule_save()

    def _on_vol_change(self, val):
        self._vol_value_lbl.config(text=f"{int(float(val))}")
        self._schedule_save()

    def _on_rate_change(self, val):
        self._rate_value_lbl.config(text=f"{int(float(val))} 词/分")
        self._schedule_save()

    def _refresh_labels(self):
        self._vol_value_lbl.config(text=f"{int(self._vol_scale.get())}")
        self._rate_value_lbl.config(text=f"{int(self._rate_scale.get())} 词/分")

    def flush_pending(self) -> None:
        get_voice().stop()
        super().flush_pending()

    def _on_preview(self):
        get_voice().stop()
        get_voice().speak_formula(self._preview_text.get() or "2 加 3 等于 5")
