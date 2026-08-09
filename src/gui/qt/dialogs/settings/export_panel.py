"""导出图片设置面板（user_config.json::export_defaults，app_config 提供默认值）。"""
from PySide6.QtWidgets import (
    QCheckBox, QGridLayout, QHBoxLayout, QLabel, QPushButton, QSpinBox,
    QVBoxLayout,
)

from .....config_loader import load_app, load_user, save_user
from .....export_config import ExportDefaults, PriceListSettings, TextColors
from ....theme import TEXT_PRIMARY
from .base import BasePanel, ColorField, normalize_hex_color, separator


class ExportPanel(BasePanel):
    def title_text(self) -> str:
        return "🖼 导出图片"

    def hint_text(self) -> str:
        return "这些选项作为导出图片对话框的默认值，写入 user_config.json。"

    def build(self, layout: QVBoxLayout) -> None:
        # ── 价目表 ──
        pl_title = QLabel("📋 价目表导出设置")
        pl_title.setStyleSheet("font-size: 14px; font-weight: bold;")
        layout.addWidget(pl_title)

        self._show_trade = QCheckBox("显示价目表")
        self._show_no_unit = QCheckBox("显示无单价项目")
        self._show_empty_cats = QCheckBox("显示无工作条目的分类")
        self._align_price_list = QCheckBox("价目表列对齐")
        layout.addWidget(self._show_trade)
        layout.addWidget(self._show_no_unit)
        layout.addWidget(self._show_empty_cats)
        layout.addWidget(self._align_price_list)

        widths = QHBoxLayout()
        widths.setSpacing(10)
        name_label = QLabel("名称列宽")
        name_label.setStyleSheet(f"color: {TEXT_PRIMARY};")
        widths.addWidget(name_label)
        self._name_width = QSpinBox()
        self._name_width.setRange(4, 40)
        widths.addWidget(self._name_width)
        price_label = QLabel("价格列宽")
        price_label.setStyleSheet(f"color: {TEXT_PRIMARY};")
        widths.addWidget(price_label)
        self._price_width = QSpinBox()
        self._price_width.setRange(4, 30)
        widths.addWidget(self._price_width)
        widths.addStretch(1)
        layout.addLayout(widths)
        layout.addWidget(separator())

        # ── 文字颜色 ──
        tc_title = QLabel("🎨 文字颜色")
        tc_title.setStyleSheet("font-size: 14px; font-weight: bold;")
        layout.addWidget(tc_title)
        colors = QGridLayout()
        colors.setHorizontalSpacing(14)
        colors.setVerticalSpacing(4)
        self._normal_color = ColorField("#000000")
        self._muted_color = ColorField("#888888")
        self._formula_color = ColorField("#007aff")
        self._amount_color = ColorField("#ff3b30")
        for row, (label, field) in enumerate((
                ("普通文字", self._normal_color),
                ("不重要文字", self._muted_color),
                ("公式", self._formula_color),
                ("金额", self._amount_color))):
            name = QLabel(label)
            name.setStyleSheet(f"color: {TEXT_PRIMARY};")
            colors.addWidget(name, row, 0)
            colors.addWidget(field, row, 1)
        layout.addLayout(colors)
        layout.addWidget(separator())

        # ── 日期显示 ──
        date_title = QLabel("📅 日期显示")
        date_title.setStyleSheet("font-size: 14px; font-weight: bold;")
        layout.addWidget(date_title)
        self._show_date = QCheckBox("显示项目日期")
        self._show_project_created_at = QCheckBox("显示项目存档创建日期")
        self._show_record_time = QCheckBox("显示每条账单记录的录入时间")
        self._show_export_time = QCheckBox("显示导出图片的时间")
        layout.addWidget(self._show_date)
        layout.addWidget(self._show_project_created_at)
        layout.addWidget(self._show_record_time)
        layout.addWidget(self._show_export_time)
        layout.addWidget(separator())

        # ── 其他设置 ──
        other_title = QLabel("⚙ 其他设置")
        other_title.setStyleSheet("font-size: 14px; font-weight: bold;")
        layout.addWidget(other_title)
        self._strip_cat = QCheckBox("精简分类信息")
        self._append_note_to_title = QCheckBox("备注追加到条目标题")
        layout.addWidget(self._strip_cat)
        layout.addWidget(self._append_note_to_title)
        bg_row = QHBoxLayout()
        bg_label = QLabel("背景颜色")
        bg_label.setStyleSheet(f"color: {TEXT_PRIMARY};")
        bg_row.addWidget(bg_label)
        self._bg_color = ColorField("#ffffff")
        bg_row.addWidget(self._bg_color)
        bg_row.addStretch(1)
        layout.addLayout(bg_row)
        layout.addWidget(separator())

        restore_btn = QPushButton("恢复默认设置")
        restore_btn.setProperty("secondary", True)
        restore_btn.clicked.connect(self._restore_defaults)
        layout.addWidget(restore_btn)
        layout.addStretch(1)

        self._show_trade.toggled.connect(self._sync_price_list_deps)
        self._align_price_list.toggled.connect(self._sync_price_list_deps)

    # ── 加载 / 保存 ────────────────────────────────────────────────────

    def _merged_defaults(self) -> ExportDefaults:
        user_cfg = load_user()
        app_export_cfg = load_app().get("export_defaults", {})
        merged = {**app_export_cfg, **user_cfg.get("export_defaults", {})}
        return ExportDefaults.from_dict(merged)

    def load(self) -> None:
        ec = self._merged_defaults()
        self._show_trade.setChecked(ec.price_list_settings.visible)
        self._show_no_unit.setChecked(ec.price_list_settings.show_no_unit_items)
        self._show_empty_cats.setChecked(ec.price_list_settings.show_empty_categories)
        self._align_price_list.setChecked(ec.price_list_settings.align_columns)
        self._name_width.setValue(ec.price_list_settings.name_width)
        self._price_width.setValue(ec.price_list_settings.price_width)
        defaults = ExportDefaults()
        self._normal_color.setText(normalize_hex_color(ec.text_colors.normal, defaults.text_colors.normal))
        self._muted_color.setText(normalize_hex_color(ec.text_colors.muted, defaults.text_colors.muted))
        self._formula_color.setText(normalize_hex_color(ec.text_colors.formula, defaults.text_colors.formula))
        self._amount_color.setText(normalize_hex_color(ec.text_colors.amount, defaults.text_colors.amount))
        self._show_date.setChecked(ec.show_project_date)
        self._show_project_created_at.setChecked(ec.show_project_created_at)
        self._show_record_time.setChecked(ec.show_record_time)
        self._show_export_time.setChecked(ec.show_export_time)
        self._strip_cat.setChecked(ec.strip_category)
        self._append_note_to_title.setChecked(ec.append_note_to_item_title)
        self._bg_color.setText(normalize_hex_color(ec.bg_color, defaults.bg_color))
        self._sync_price_list_deps()

    def save(self) -> None:
        defaults = ExportDefaults()
        cfg = ExportDefaults(
            price_list_settings=PriceListSettings(
                visible=self._show_trade.isChecked(),
                show_no_unit_items=self._show_no_unit.isChecked(),
                show_empty_categories=self._show_empty_cats.isChecked(),
                align_columns=self._align_price_list.isChecked(),
                name_width=max(1, self._name_width.value()),
                price_width=max(1, self._price_width.value()),
            ),
            text_colors=TextColors(
                normal=normalize_hex_color(self._normal_color.text(), defaults.text_colors.normal),
                muted=normalize_hex_color(self._muted_color.text(), defaults.text_colors.muted),
                formula=normalize_hex_color(self._formula_color.text(), defaults.text_colors.formula),
                amount=normalize_hex_color(self._amount_color.text(), defaults.text_colors.amount),
            ),
            bg_color=normalize_hex_color(self._bg_color.text(), defaults.bg_color),
            strip_category=self._strip_cat.isChecked(),
            show_project_date=self._show_date.isChecked(),
            show_project_created_at=self._show_project_created_at.isChecked(),
            show_record_time=self._show_record_time.isChecked(),
            show_export_time=self._show_export_time.isChecked(),
            append_note_to_item_title=self._append_note_to_title.isChecked(),
        )
        user_cfg = load_user()
        user_cfg["export_defaults"] = cfg.to_dict()
        save_user(user_cfg)

    # ── 依赖同步 / 恢复默认 ────────────────────────────────────────────

    def _sync_price_list_deps(self) -> None:
        enabled = self._show_trade.isChecked()
        for cb in (self._show_no_unit, self._show_empty_cats, self._align_price_list):
            cb.setEnabled(enabled)
        width_enabled = enabled and self._align_price_list.isChecked()
        self._name_width.setEnabled(width_enabled)
        self._price_width.setEnabled(width_enabled)
        if not enabled:
            self._show_no_unit.setChecked(False)

    def _restore_defaults(self) -> None:
        d = ExportDefaults.from_dict(load_app().get("export_defaults", {}))
        self._show_trade.setChecked(d.price_list_settings.visible)
        self._show_no_unit.setChecked(d.price_list_settings.show_no_unit_items)
        self._show_empty_cats.setChecked(d.price_list_settings.show_empty_categories)
        self._align_price_list.setChecked(d.price_list_settings.align_columns)
        self._name_width.setValue(d.price_list_settings.name_width)
        self._price_width.setValue(d.price_list_settings.price_width)
        self._normal_color.setText(d.text_colors.normal)
        self._muted_color.setText(d.text_colors.muted)
        self._formula_color.setText(d.text_colors.formula)
        self._amount_color.setText(d.text_colors.amount)
        self._show_date.setChecked(d.show_project_date)
        self._show_project_created_at.setChecked(d.show_project_created_at)
        self._show_record_time.setChecked(d.show_record_time)
        self._show_export_time.setChecked(d.show_export_time)
        self._strip_cat.setChecked(d.strip_category)
        self._append_note_to_title.setChecked(d.append_note_to_item_title)
        self._bg_color.setText(d.bg_color)
        self._sync_price_list_deps()
        self.save()
