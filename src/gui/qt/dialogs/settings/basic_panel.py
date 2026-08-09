"""基础设置面板：默认字号 / 备份数量 / 账单行颜色 / 符号映射展示。"""
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QHBoxLayout, QLabel, QPlainTextEdit, QSlider, QSpinBox, QVBoxLayout,
)

from .....config_loader import load_app, save_app
from .....symbol_mapping import DEFAULT_SYMBOL_MAPPING, normalize_symbol_mapping
from ....font_manager import font_manager
from ....theme import ACCENT, REVIEW_BG, TEXT_PRIMARY
from .base import BasePanel, color_row, normalize_hex_color, section_hint, separator


class BasicPanel(BasePanel):
    def title_text(self) -> str:
        return "⚙ 基础设置"

    def hint_text(self) -> str:
        return "这些设置会写入 app_config.json，作为应用级默认值。"

    def build(self, layout: QVBoxLayout) -> None:
        # ── 默认字号 ──
        size_row = QHBoxLayout()
        size_row.setSpacing(8)
        label = QLabel("默认字号")
        label.setStyleSheet(f"color: {TEXT_PRIMARY};")
        label.setFixedWidth(90)
        size_row.addWidget(label)

        self._size_slider = QSlider()
        self._size_slider.setOrientation(Qt.Horizontal)
        self._size_slider.setRange(10, 30)
        size_row.addWidget(self._size_slider, 1)

        self._size_value = QLabel()
        self._size_value.setFixedWidth(48)
        size_row.addWidget(self._size_value)
        layout.addLayout(size_row)
        layout.addWidget(section_hint("全局基础字号决定所有角色的默认大小。"))
        layout.addWidget(separator())

        # ── 备份数量 ──
        backup_row = QHBoxLayout()
        backup_row.setSpacing(8)
        backup_label = QLabel("备份数量")
        backup_label.setStyleSheet(f"color: {TEXT_PRIMARY};")
        backup_label.setFixedWidth(90)
        backup_row.addWidget(backup_label)

        self._backup_count = QSpinBox()
        self._backup_count.setRange(1, 100)
        backup_row.addWidget(self._backup_count)
        backup_row.addStretch(1)
        layout.addLayout(backup_row)
        layout.addWidget(section_hint("每个项目最多保留的备份文件数。"))
        layout.addWidget(separator())

        # ── 账单管理设置 ──
        title = QLabel("账单管理设置")
        title.setStyleSheet("font-size: 14px; font-weight: bold;")
        layout.addWidget(title)
        layout.addWidget(section_hint("颜色值使用 #RRGGBB 格式；选中颜色优先于已审核行颜色。"))
        self._selection_color = color_row(layout, "选中行颜色", ACCENT, lambda c: None)
        self._reviewed_color = color_row(layout, "已审核行颜色", REVIEW_BG, lambda c: None)
        layout.addWidget(separator())

        # ── 符号映射（只读展示） ──
        mapping_title = QLabel("符号映射")
        mapping_title.setStyleSheet("font-size: 14px; font-weight: bold;")
        layout.addWidget(mapping_title)
        layout.addWidget(section_hint(
            "符号映射从 app_config.json 读取，仅在此展示；如需修改请编辑配置文件。"
        ))
        self._symbol_display = QPlainTextEdit()
        self._symbol_display.setReadOnly(True)
        self._symbol_display.setMaximumBlockCount(0)
        self._symbol_display.setMinimumHeight(100)
        self._symbol_display.setMaximumHeight(220)
        layout.addWidget(self._symbol_display)
        layout.addStretch(1)

    # ── 加载 / 保存 ────────────────────────────────────────────────────

    def load(self) -> None:
        cfg = load_app()
        try:
            size = int(cfg.get("default_font_size", 14))
        except (TypeError, ValueError):
            size = 14
        self._size_slider.setValue(size)
        self._size_value.setText(f"{size}px")
        self._size_slider.valueChanged.connect(self._on_size_changed)

        self._backup_count.setValue(max(1, min(100, int(cfg.get("backup_count", 10)))))
        self._selection_color.setText(
            normalize_hex_color(cfg.get("selection_highlight_color"), ACCENT)
        )
        self._reviewed_color.setText(
            normalize_hex_color(cfg.get("bill_reviewed_row_color"), REVIEW_BG)
        )

        mapping = normalize_symbol_mapping(cfg.get("symbol_mapping") or DEFAULT_SYMBOL_MAPPING)
        lines = ["运算符："]
        for canonical in ("+", "-", "*", "/"):
            item = mapping["operators"][canonical]
            aliases = " ".join(item.get("aliases", [])) or "无"
            lines.append(f"  {canonical}  {item.get('label', '')}  别名：{aliases}"
                         f"  语音：{item.get('voice_key', canonical)}")
        lines.append("")
        lines.append("括号对：")
        for pair in mapping.get("bracket_pairs", []):
            lines.append(
                f"  {pair['left']} {pair['right']}  {pair['left_label']} / "
                f"{pair['right_label']}  语音：{pair.get('voice_left_key', '(')} / "
                f"{pair.get('voice_right_key', ')')}"
            )
        self._symbol_display.setPlainText("\n".join(lines))

    def _on_size_changed(self, value: int) -> None:
        self._size_value.setText(f"{value}px")

    def save(self) -> None:
        cfg = load_app()
        cfg["backup_count"] = self._backup_count.value()
        cfg["selection_highlight_color"] = normalize_hex_color(
            self._selection_color.text(), ACCENT
        )
        cfg["bill_reviewed_row_color"] = normalize_hex_color(
            self._reviewed_color.text(), REVIEW_BG
        )
        save_app(cfg)
        font_manager.save_default_font_size(self._size_slider.value())
