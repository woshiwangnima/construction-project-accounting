"""通知设置面板 — Toast 显示行为配置（app_config.json::toast_settings）。"""
from PySide6.QtWidgets import QHBoxLayout, QLabel, QSpinBox, QVBoxLayout

from .....config_loader import load_app, save_app
from ....theme import TEXT_PRIMARY
from .base import BasePanel, section_hint, separator

_KEY = "toast_settings"

_DEFAULTS = {
    "duration_ms": 5000,
    "fade_in_ms": 300,
    "float_ms": 700,
    "queue_interval_ms": 1000,
}


class NotificationPanel(BasePanel):
    def title_text(self) -> str:
        return "🔔 通知"

    def hint_text(self) -> str:
        return "配置 Toast 通知的显示时长与排队间隔，写入 app_config.json。"

    def build(self, layout: QVBoxLayout) -> None:
        # 飘动持续时间
        duration_title = QLabel("飘动持续时间（秒）")
        duration_title.setStyleSheet("font-size: 14px; font-weight: bold;")
        layout.addWidget(duration_title)
        dur_row = QHBoxLayout()
        dur_row.setSpacing(8)
        self._duration = QSpinBox()
        self._duration.setRange(1, 60)
        dur_row.addWidget(self._duration)
        dur_row.addWidget(QLabel("秒"))
        dur_row.addStretch(1)
        layout.addLayout(dur_row)
        layout.addWidget(separator())

        # 队列间隔时间
        queue_title = QLabel("队列间隔时间（秒）")
        queue_title.setStyleSheet("font-size: 14px; font-weight: bold;")
        layout.addWidget(queue_title)
        queue_row = QHBoxLayout()
        queue_row.setSpacing(8)
        self._queue_interval = QSpinBox()
        self._queue_interval.setRange(1, 10)
        queue_row.addWidget(self._queue_interval)
        queue_row.addWidget(QLabel("秒"))
        queue_row.addStretch(1)
        layout.addLayout(queue_row)
        layout.addWidget(section_hint("队列中有多条通知时，每条仅展示此时间。"))
        layout.addStretch(1)

    # ── 加载 / 保存 ────────────────────────────────────────────────────

    def load(self) -> None:
        s = load_app().get(_KEY, {}) or {}
        try:
            duration = max(1, min(60, int(s.get("duration_ms", _DEFAULTS["duration_ms"])) // 1000))
        except (TypeError, ValueError):
            duration = _DEFAULTS["duration_ms"] // 1000
        try:
            queue_interval = max(
                1, min(10, int(s.get("queue_interval_ms", _DEFAULTS["queue_interval_ms"])) // 1000)
            )
        except (TypeError, ValueError):
            queue_interval = _DEFAULTS["queue_interval_ms"] // 1000
        self._duration.setValue(duration)
        self._queue_interval.setValue(queue_interval)

    def save(self) -> None:
        cfg = load_app()
        d = cfg.setdefault(_KEY, {})
        d["duration_ms"] = max(1, min(60, self._duration.value())) * 1000
        d["fade_in_ms"] = _DEFAULTS["fade_in_ms"]
        d["float_ms"] = _DEFAULTS["float_ms"]
        d["queue_interval_ms"] = max(1, min(10, self._queue_interval.value())) * 1000
        save_app(cfg)
