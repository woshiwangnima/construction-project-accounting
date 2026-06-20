"""通知设置面板 — Toast 显示行为配置。"""

import tkinter as tk
from ....config_loader import load_app, save_app
from ...theme import APP_BG, TEXT_PRIMARY
from ...font_manager import font_manager
from .base import BaseSettingsPanel, register_section


_KEY = "toast_settings"

_DEFAULTS = {
    "duration_ms": 5000,
    "fade_in_ms": 300,
    "float_ms": 700,
    "queue_interval_ms": 1000,
}


@register_section
class NotificationSettingsPanel(BaseSettingsPanel):
    section_id = "notification"
    section_title = "通知"
    section_icon = "\U0001f514"
    section_order = 50

    def _build(self):
        self._vars = {}

        tk.Label(self, text="飘动持续时间（秒）", font=font_manager.get("body_bold"),
                 bg=APP_BG, fg=TEXT_PRIMARY).pack(anchor="w", pady=(0, 8))
        dur_frame = tk.Frame(self, bg=APP_BG)
        dur_frame.pack(fill=tk.X, pady=(0, 16))
        self._vars["duration"] = tk.StringVar(value="5")
        sp = tk.Spinbox(dur_frame, from_=1, to=60,
                        textvariable=self._vars["duration"],
                        font=font_manager.get("body"), width=8,
                        command=self._schedule_save, bg="white")
        sp.pack(side=tk.LEFT)
        sp.bind("<KeyRelease>", lambda e: self._schedule_save())
        tk.Label(dur_frame, text="秒", font=font_manager.get("body"),
                 bg=APP_BG, fg=TEXT_PRIMARY).pack(side=tk.LEFT, padx=(6, 0))

        tk.Label(self, text="队列间隔时间（秒）", font=font_manager.get("body_bold"),
                 bg=APP_BG, fg=TEXT_PRIMARY).pack(anchor="w", pady=(0, 8))
        q_frame = tk.Frame(self, bg=APP_BG)
        q_frame.pack(fill=tk.X, pady=(0, 16))
        self._vars["queue_interval"] = tk.StringVar(value="1")
        qs = tk.Spinbox(q_frame, from_=1, to=10,
                        textvariable=self._vars["queue_interval"],
                        font=font_manager.get("body"), width=8,
                        command=self._schedule_save, bg="white")
        qs.pack(side=tk.LEFT)
        qs.bind("<KeyRelease>", lambda e: self._schedule_save())
        tk.Label(q_frame, text="秒", font=font_manager.get("body"),
                 bg=APP_BG, fg=TEXT_PRIMARY).pack(side=tk.LEFT, padx=(6, 0))
        tk.Label(q_frame, text="队列中有多条通知时，每条仅展示此时间",
                 font=font_manager.get("small"), bg=APP_BG, fg=TEXT_PRIMARY).pack(side=tk.LEFT, padx=(12, 0))

    def _load(self):
        s = load_app().get(_KEY, {})
        self._vars["duration"].set(str(s.get("duration_ms", _DEFAULTS["duration_ms"]) // 1000))
        self._vars["queue_interval"].set(str(s.get("queue_interval_ms", _DEFAULTS["queue_interval_ms"]) // 1000))

    def _save(self):
        cfg = load_app()
        d = cfg.setdefault(_KEY, {})
        try:
            d["duration_ms"] = max(1, int(self._vars["duration"].get())) * 1000
        except ValueError:
            d["duration_ms"] = _DEFAULTS["duration_ms"]
        d["fade_in_ms"] = _DEFAULTS["fade_in_ms"]
        d["float_ms"] = _DEFAULTS["float_ms"]
        try:
            d["queue_interval_ms"] = max(1, int(self._vars["queue_interval"].get())) * 1000
        except ValueError:
            d["queue_interval_ms"] = _DEFAULTS["queue_interval_ms"]
        save_app(cfg)
