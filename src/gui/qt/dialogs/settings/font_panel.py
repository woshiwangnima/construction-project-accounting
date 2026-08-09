"""字体设置面板：各角色字体族 / 字号 / 样式 / 颜色 + 预览。"""
from PySide6.QtGui import QFont, QFontDatabase
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QHBoxLayout, QLabel, QSpinBox, QVBoxLayout,
)

from ....font_manager import (
    font_manager, ROLE_GROUPS, ROLE_KEYS, ROLE_DISPLAY_NAMES,
)
from .base import (
    BasePanel, ColorField, normalize_hex_color, separator,
)

_PREVIEW_TEXT = "预览 Ab 123"
_DEFAULT_FAMILY = "Microsoft YaHei UI"

# 常用字体白名单：真实 Windows 有数百种字体，全部塞进 14 个下拉框会
# 导致面板构建数秒、点击切换卡死。仅列出主流中英文字体，够用且快。
_PREFERRED_FAMILIES = (
    "Microsoft YaHei UI", "Microsoft YaHei", "SimHei", "SimSun",
    "KaiTi", "FangSong", "DengXian", "NSimSun",
    "Segoe UI", "Arial", "Calibri", "Tahoma", "Times New Roman",
    "Consolas", "Courier New", "Microsoft JhengHei",
)


class FontPanel(BasePanel):
    def title_text(self) -> str:
        return "🔤 字体设置"

    def hint_text(self) -> str:
        return ("角色字号由「默认字号 × 倍率」计算；此处可改字体族与样式，"
                "设置写入 user_config.json 的 font_settings。")

    def build(self, layout: QVBoxLayout) -> None:
        # 只枚举白名单字体 + 用户当前使用的字体，避免几百个字体 × 14 下拉框
        # 导致构建卡顿（真实 Windows 字体库很大）。
        all_families = QFontDatabase.families()
        self._families = [
            f for f in _PREFERRED_FAMILIES if f in all_families
        ]
        settings = font_manager.get_all_settings()
        for _role, cfg in settings.items():
            family = cfg.get("family") or _DEFAULT_FAMILY
            if family and family in all_families and family not in self._families:
                self._families.append(family)
        if not self._families:
            self._families = list(all_families)
        self._rows: dict[str, dict] = {}

        for group_name, role_keys in ROLE_GROUPS:
            layout.addWidget(separator())
            group = QLabel(group_name)
            group.setStyleSheet("font-size: 14px; font-weight: bold;")
            layout.addWidget(group)
            for role in role_keys:
                if role not in ROLE_KEYS:
                    continue
                self._build_role_row(layout, role)

        layout.addWidget(separator())

    def _build_role_row(self, layout: QVBoxLayout, role: str) -> None:
        rv: dict = {}

        label = QLabel(f"  {ROLE_DISPLAY_NAMES[role]}")
        layout.addWidget(label)

        family_row = QHBoxLayout()
        family_row.setSpacing(8)
        combo = QComboBox()
        combo.setEditable(False)
        combo.addItems(self._families)
        combo.setMinimumWidth(180)
        family_row.addWidget(combo, 1)

        size_spin = QSpinBox()
        size_spin.setRange(8, 72)
        family_row.addWidget(size_spin)

        color_field = ColorField("#000000", on_change=lambda *_: self._on_change(role))
        family_row.addWidget(color_field)
        layout.addLayout(family_row)

        style_row = QHBoxLayout()
        style_row.setSpacing(4)
        for key, text in (("bold", "B"), ("italic", "I"),
                          ("underline", "U"), ("overstrike", "S")):
            cb = QCheckBox(text)
            cb.setStyleSheet(
                "font-weight: bold;" if key == "bold" else
                "font-style: italic;" if key == "italic" else ""
            )
            cb.toggled.connect(lambda *_, r=role: self._on_change(r))
            style_row.addWidget(cb)
            rv[key] = cb
        style_row.addStretch(1)
        layout.addLayout(style_row)

        preview = QLabel(_PREVIEW_TEXT)
        preview.setFixedHeight(28)
        layout.addWidget(preview)

        rv["family"] = combo
        rv["size"] = size_spin
        rv["color"] = color_field
        rv["preview"] = preview
        rv["_loaded"] = False

        combo.currentTextChanged.connect(lambda *_, r=role: self._on_change(r))
        size_spin.valueChanged.connect(lambda *_, r=role: self._on_change(r))

        self._rows[role] = rv
        self._apply_preview(role, _defaults_for(role))

    # ── 交互 ────────────────────────────────────────────────────────────

    def _on_change(self, role: str) -> None:
        rv = self._rows[role]
        if not rv.get("_loaded"):
            return
        self._apply_preview(role, self._read_row(role))

    def _read_row(self, role: str) -> dict:
        rv = self._rows[role]
        return {
            "family": rv["family"].currentText(),
            "size": rv["size"].value(),
            "bold": rv["bold"].isChecked(),
            "italic": rv["italic"].isChecked(),
            "underline": rv["underline"].isChecked(),
            "overstrike": rv["overstrike"].isChecked(),
            "color": normalize_hex_color(rv["color"].text(), "#000000"),
        }

    def _apply_preview(self, role: str, cfg: dict) -> None:
        rv = self._rows[role]
        font = QFont(cfg["family"] or _DEFAULT_FAMILY, max(1, int(cfg.get("size", 14))))
        font.setWeight(QFont.Weight.Bold if cfg.get("bold") else QFont.Weight.Normal)
        font.setItalic(bool(cfg.get("italic")))
        font.setUnderline(bool(cfg.get("underline")))
        font.setStrikeOut(bool(cfg.get("overstrike")))
        rv["preview"].setFont(font)
        color = normalize_hex_color(cfg.get("color"), "#000000")
        rv["preview"].setStyleSheet(f"color: {color};")

    # ── 加载 / 保存 ────────────────────────────────────────────────────

    def load(self) -> None:
        settings = font_manager.get_all_settings()
        for role, rv in self._rows.items():
            cfg = settings.get(role) or _defaults_for(role)
            family = cfg.get("family") or _DEFAULT_FAMILY
            if family not in self._families:
                family = _DEFAULT_FAMILY
            rv["family"].setCurrentText(family)
            rv["size"].setValue(int(cfg.get("size", 14)))
            rv["bold"].setChecked(bool(cfg.get("bold")))
            rv["italic"].setChecked(bool(cfg.get("italic")))
            rv["underline"].setChecked(bool(cfg.get("underline")))
            rv["overstrike"].setChecked(bool(cfg.get("overstrike")))
            rv["color"].setText(normalize_hex_color(cfg.get("color"), "#000000"))
            self._apply_preview(role, cfg)
            rv["_loaded"] = True

    def save(self) -> None:
        settings = {}
        for role in self._rows:
            settings[role] = self._read_row(role)
        font_manager.save_settings(settings)
        font_manager.refresh()


def _defaults_for(role: str) -> dict:
    return {
        "family": _DEFAULT_FAMILY,
        "size": 14,
        "bold": False,
        "italic": False,
        "underline": False,
        "overstrike": False,
        "color": "#1c1c1e",
    }
