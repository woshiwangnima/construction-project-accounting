"""语音播报设置面板：启用开关 / 音量 / 语速 / 试播。

存储位置：app_config.json::voice；保存后调用 VoiceEngine.reload()。
"""
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QHBoxLayout, QLabel, QPushButton, QSlider, QVBoxLayout

from qfluentwidgets import SwitchButton

from .....config_loader import load_app, save_app
from .....voice import get_voice
from ....theme import TEXT_PRIMARY, TEXT_SECONDARY
from .base import BasePanel, section_hint, separator

VOL_MIN, VOL_MAX = 0, 100
RATE_MIN, RATE_MAX = 50, 400


class VoicePanel(BasePanel):
    def title_text(self) -> str:
        return "🎙 语音播报"

    def hint_text(self) -> str:
        return "设置写入 app_config.json::voice；保存后立即生效。"

    def build(self, layout: QVBoxLayout) -> None:
        self._enabled = SwitchButton("启用语音播报（按键音 + 公式朗读）")
        layout.addWidget(self._enabled)
        layout.addWidget(separator())

        # 音量
        vol_title = QLabel("🔊 音量")
        vol_title.setStyleSheet("font-size: 14px; font-weight: bold;")
        layout.addWidget(vol_title)
        layout.addWidget(section_hint("影响按键音（WAV）和公式朗读音量。"))
        self._volume, self._volume_value = self._make_slider(
            layout, VOL_MIN, VOL_MAX, ""
        )
        layout.addWidget(separator())

        # 语速
        rate_title = QLabel("🗣 公式朗读语速")
        rate_title.setStyleSheet("font-size: 14px; font-weight: bold;")
        layout.addWidget(rate_title)
        layout.addWidget(section_hint("仅影响 🔊 朗读按钮；不影响 0–9、运算符等按键音速度。"))
        self._rate, self._rate_value = self._make_slider(
            layout, RATE_MIN, RATE_MAX, " 词/分"
        )
        layout.addWidget(separator())

        self._preview_text = QLabel("")
        self._preview_text.setStyleSheet(f"color: {TEXT_SECONDARY}; font-size: 12px;")
        self._preview_text.setWordWrap(True)
        preview_btn = QPushButton("▶ 试播示例")
        preview_btn.setProperty("secondary", True)
        preview_btn.clicked.connect(self._on_preview)
        layout.addWidget(preview_btn)
        layout.addWidget(self._preview_text)
        layout.addStretch(1)

    def _make_slider(self, layout, frm: int, to: int, suffix: str):
        row = QHBoxLayout()
        row.setSpacing(8)
        slider = QSlider()
        slider.setOrientation(Qt.Horizontal)
        slider.setRange(frm, to)
        row.addWidget(slider, 1)
        value = QLabel()
        value.setFixedWidth(72)
        row.addWidget(value)
        layout.addLayout(row)
        return slider, (value, suffix)

    # ── 加载 / 保存 ────────────────────────────────────────────────────

    def load(self) -> None:
        cfg = load_app()
        voice = cfg.get("voice", {}) or {}
        self._enabled.setChecked(bool(voice.get("enabled", True)))
        self._volume.setValue(int(voice.get("volume", 80)))
        self._rate.setValue(int(voice.get("tts_rate", 150)))
        self._preview_text.setText(
            str(voice.get("preview_text") or "2 加 3 等于 5")
        )
        self._refresh_labels()
        self._volume.valueChanged.connect(self._refresh_labels)
        self._rate.valueChanged.connect(self._refresh_labels)

    def _refresh_labels(self) -> None:
        vol_lbl, vol_suffix = self._volume_value
        vol_lbl.setText(f"{self._volume.value()}{vol_suffix}")
        rate_lbl, rate_suffix = self._rate_value
        rate_lbl.setText(f"{self._rate.value()}{rate_suffix}")

    def save(self) -> None:
        cfg = load_app()
        voice = cfg.setdefault("voice", {})
        voice["enabled"] = self._enabled.isChecked()
        voice["volume"] = self._volume.value()
        voice["tts_rate"] = self._rate.value()
        voice.setdefault("preview_text", self._preview_text.text())
        save_app(cfg)
        get_voice().reload()

    def _on_preview(self) -> None:
        get_voice().stop()
        get_voice().speak_formula(self._preview_text.text() or "2 加 3 等于 5")
