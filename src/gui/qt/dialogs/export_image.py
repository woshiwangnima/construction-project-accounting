"""导出记账图片对话框（Qt）。

选项来自 src/export_config.py 的 ExportDefaults（合并 app_config 默认值与
user_config 覆盖）；渲染复用 src/image_output.py 的 save_styled_image。
成功后回调 on_done()。
"""
import os
import sys
from datetime import datetime

from PySide6.QtWidgets import (
    QCheckBox, QDialog, QFileDialog, QFrame, QGridLayout, QHBoxLayout, QLabel,
    QLineEdit, QMessageBox, QPushButton, QScrollArea, QSpinBox, QVBoxLayout,
    QWidget,
)

from ....billing import read_billing
from ....bill_recompute import prepare_bill_calculations
from ....calculator import to_canonical, to_display, MathParseError
from ....billing_resolver import orphan_bills
from ....config_loader import load_app, load_user
from ....export_config import ExportDefaults
from ....image_output import save_styled_image
from ....logger import logger
from ...theme import (SYSTEM_RED, TEXT_PRIMARY, TEXT_SECONDARY, font_px)


from ....export_document import build_export_blocks


def _resolve_font_path() -> str | None:
    """按平台返回中文字体路径（与 Tk 导出逻辑一致），找不到返回 None。"""
    if sys.platform == "win32":
        sr = os.environ.get("SystemRoot", "")
        if sr:
            candidate = os.path.join(sr, "Fonts", "msyh.ttc")
            if os.path.isfile(candidate):
                return candidate
    elif sys.platform == "linux":
        for fp in ("/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc",
                   "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc"):
            if os.path.isfile(fp):
                return fp
    return None


class ExportImageDialog(QDialog):
    """导出记账图片对话框。project_data 为项目 dict。"""

    def __init__(self, parent, project_data: dict, on_done=None):
        super().__init__(parent)
        self.project_data = project_data or {}
        self.on_done = on_done

        self.setWindowTitle("导出图片")
        self.setModal(True)
        self.setMinimumSize(560, 420)
        self.resize(620, 520)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 16, 20, 16)
        layout.setSpacing(10)

        title = QLabel("导出记账图片")
        title.setStyleSheet(f"font-size: {font_px('heading')}px; font-weight: bold;")
        layout.addWidget(title)

        hint = QLabel("勾选导出选项后选择保存位置。")
        hint.setStyleSheet(f"color: {TEXT_SECONDARY};")
        layout.addWidget(hint)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        body = QWidget()
        body_layout = QVBoxLayout(body)
        body_layout.setContentsMargins(0, 0, 0, 0)
        body_layout.setSpacing(6)

        self._vars: dict[str, object] = {}
        self._build_sections(body, body_layout)

        scroll.setWidget(body)
        layout.addWidget(scroll, 1)

        path_row = QHBoxLayout()
        path_label = QLabel("保存路径")
        path_label.setStyleSheet(f"color: {TEXT_SECONDARY};")
        path_label.setFixedWidth(70)
        self._path_edit = _readonly_line_edit()
        self._path_edit.setPlaceholderText("未选择（点击右侧按钮选择）")
        browse_btn = QPushButton("选择…")
        browse_btn.setProperty("secondary", True)
        browse_btn.clicked.connect(self._browse_path)
        path_row.addWidget(path_label)
        path_row.addWidget(self._path_edit, 1)
        path_row.addWidget(browse_btn)
        layout.addLayout(path_row)

        btn_row = QHBoxLayout()
        btn_row.addStretch(1)
        self._export_btn = QPushButton("导出")
        self._export_btn.clicked.connect(self._do_export)
        btn_row.addWidget(self._export_btn)
        cancel_btn = QPushButton("取消")
        cancel_btn.setProperty("secondary", True)
        cancel_btn.clicked.connect(self.reject)
        btn_row.addWidget(cancel_btn)
        layout.addLayout(btn_row)

        self._load_defaults()

    # ── 选项构建 ───────────────────────────────────────────────────────

    def _section(self, parent_layout, text: str) -> QGridLayout:
        label = QLabel(text)
        label.setStyleSheet(f"font-size: {font_px('subheading')}px; font-weight: bold;")
        parent_layout.addWidget(label)
        grid = QGridLayout()
        grid.setContentsMargins(4, 0, 0, 0)
        grid.setHorizontalSpacing(10)
        grid.setVerticalSpacing(4)
        parent_layout.addLayout(grid)
        return grid

    def _build_sections(self, body, body_layout):
        # 价目表
        pl = self._section(body_layout, "价目表导出设置")
        self._show_trade = QCheckBox("显示价目表")
        self._show_no_unit = QCheckBox("显示无单价项目")
        self._show_empty_cats = QCheckBox("显示无工作条目的分类")
        self._align_price_list = QCheckBox("价目表列对齐")
        pl.addWidget(self._show_trade, 0, 0)
        pl.addWidget(self._show_no_unit, 0, 1)
        pl.addWidget(self._show_empty_cats, 1, 0)
        pl.addWidget(self._align_price_list, 1, 1)

        self._name_width = QSpinBox()
        self._name_width.setRange(4, 40)
        self._price_width = QSpinBox()
        self._price_width.setRange(4, 30)
        pl.addWidget(QLabel("名称列宽"), 2, 0)
        pl.addWidget(self._name_width, 2, 1)
        pl.addWidget(QLabel("价格列宽"), 3, 0)
        pl.addWidget(self._price_width, 3, 1)

        self._show_trade.toggled.connect(self._sync_price_list_deps)
        self._align_price_list.toggled.connect(self._sync_price_list_deps)

        # 文字颜色
        tc = self._section(body_layout, "文字颜色")
        self._normal_color = _readonly_line_edit()
        self._muted_color = _readonly_line_edit()
        self._formula_color = _readonly_line_edit()
        self._amount_color = _readonly_line_edit()
        for row, (label, editor) in enumerate((
                ("普通文字", self._normal_color),
                ("不重要文字", self._muted_color),
                ("公式", self._formula_color),
                ("金额", self._amount_color))):
            tc.addWidget(QLabel(label), row, 0)
            tc.addWidget(editor, row, 1)

        # 日期显示
        dates = self._section(body_layout, "日期显示")
        self._show_date = QCheckBox("显示项目日期")
        self._show_project_created_at = QCheckBox("显示项目存档创建日期")
        self._show_record_time = QCheckBox("显示每条账单记录的录入时间")
        self._show_export_time = QCheckBox("显示导出图片的时间")
        dates.addWidget(self._show_date, 0, 0)
        dates.addWidget(self._show_project_created_at, 0, 1)
        dates.addWidget(self._show_record_time, 1, 0)
        dates.addWidget(self._show_export_time, 1, 1)

        # 其他设置
        other = self._section(body_layout, "其他设置")
        self._strip_cat = QCheckBox("精简分类信息")
        self._append_note_to_title = QCheckBox("备注追加到条目标题")
        self._bg_color = _readonly_line_edit()
        other.addWidget(self._strip_cat, 0, 0)
        other.addWidget(self._append_note_to_title, 0, 1)
        other.addWidget(QLabel("背景颜色"), 1, 0)
        other.addWidget(self._bg_color, 1, 1)

    # ── 加载 / 同步 ────────────────────────────────────────────────────

    def _load_defaults(self) -> None:
        user_cfg = load_user()
        app_export_cfg = load_app().get("export_defaults", {})
        merged = {**app_export_cfg, **user_cfg.get("export_defaults", {})}
        ec = ExportDefaults.from_dict(merged)
        self._defaults = ec
        self._show_trade.setChecked(ec.price_list_settings.visible)
        self._show_no_unit.setChecked(ec.price_list_settings.show_no_unit_items)
        self._show_empty_cats.setChecked(ec.price_list_settings.show_empty_categories)
        self._align_price_list.setChecked(ec.price_list_settings.align_columns)
        self._name_width.setValue(ec.price_list_settings.name_width)
        self._price_width.setValue(ec.price_list_settings.price_width)
        self._normal_color.setText(ec.text_colors.normal)
        self._muted_color.setText(ec.text_colors.muted)
        self._formula_color.setText(ec.text_colors.formula)
        self._amount_color.setText(ec.text_colors.amount)
        self._show_date.setChecked(ec.show_project_date)
        self._show_project_created_at.setChecked(ec.show_project_created_at)
        self._show_record_time.setChecked(ec.show_record_time)
        self._show_export_time.setChecked(ec.show_export_time)
        self._strip_cat.setChecked(ec.strip_category)
        self._append_note_to_title.setChecked(ec.append_note_to_item_title)
        self._bg_color.setText(ec.bg_color)
        self._sync_price_list_deps()

    def _sync_price_list_deps(self) -> None:
        enabled = self._show_trade.isChecked()
        self._show_no_unit.setEnabled(enabled)
        self._show_empty_cats.setEnabled(enabled)
        self._align_price_list.setEnabled(enabled)
        width_enabled = enabled and self._align_price_list.isChecked()
        self._name_width.setEnabled(width_enabled)
        self._price_width.setEnabled(width_enabled)
        if not enabled:
            self._show_no_unit.setChecked(False)

    def _current_defaults(self) -> ExportDefaults:
        from ....export_config import PriceListSettings, TextColors

        defaults = self._defaults
        return ExportDefaults(
            price_list_settings=PriceListSettings(
                visible=self._show_trade.isChecked(),
                show_no_unit_items=self._show_no_unit.isChecked(),
                show_empty_categories=self._show_empty_cats.isChecked(),
                align_columns=self._align_price_list.isChecked(),
                name_width=self._name_width.value(),
                price_width=self._price_width.value(),
            ),
            text_colors=TextColors(
                normal=_hex(self._normal_color.text(), defaults.text_colors.normal),
                muted=_hex(self._muted_color.text(), defaults.text_colors.muted),
                formula=_hex(self._formula_color.text(), defaults.text_colors.formula),
                amount=_hex(self._amount_color.text(), defaults.text_colors.amount),
            ),
            bg_color=_hex(self._bg_color.text(), defaults.bg_color),
            strip_category=self._strip_cat.isChecked(),
            show_project_date=self._show_date.isChecked(),
            show_project_created_at=self._show_project_created_at.isChecked(),
            show_record_time=self._show_record_time.isChecked(),
            show_export_time=self._show_export_time.isChecked(),
            append_note_to_item_title=self._append_note_to_title.isChecked(),
        )

    # ── 导出流程 ───────────────────────────────────────────────────────

    def _browse_path(self) -> None:
        p = self.project_data
        default_name = f"{p.get('name', '账单')}.png"
        path, _ = QFileDialog.getSaveFileName(
            self, "保存图片", default_name,
            "PNG图片 (*.png);;所有文件 (*.*)",
        )
        if path:
            self._path_edit.setText(path)

    def _do_export(self) -> None:
        p = self.project_data
        bills = p.get("bills", []) or []
        if not bills:
            QMessageBox.information(self, "提示", "暂无记录可导出")
            return

        orphans = orphan_bills(bills, p.get("trade_items", []) or [])
        if orphans:
            QMessageBox.warning(
                self,
                "存在孤儿账单",
                f"当前项目有 {len(orphans)} 条账单引用的工作项目已被删除或重命名。\n"
                "请先处理孤儿账单后再导出图片。",
            )
            return

        path = self._path_edit.text().strip()
        if not path:
            QMessageBox.warning(self, "导出图片", "请先选择保存路径。")
            return
        if not path.lower().endswith(".png"):
            path += ".png"

        op_map = load_app().get("symbol_mapping", {}) or {}
        ec = self._current_defaults()
        blocks, _total = build_export_blocks(p, op_map, ec)

        try:
            save_styled_image(
                blocks, path,
                font_path=_resolve_font_path(),
                bg_color=ec.bg_color,
                text_color=ec.text_colors.normal,
            )
        except Exception as exc:
            logger.error("导出图片失败: %s", exc)
            QMessageBox.critical(self, "错误", f"导出失败：{exc}")
            return

        display_path = os.path.normpath(path) if os.name == "nt" else path
        QMessageBox.information(self, "导出成功", f"图片已保存到：\n{display_path}")
        if self.on_done is not None:
            try:
                self.on_done()
            except Exception as exc:
                logger.debug("[export_image] on_done callback raised: %s", exc)
        self.accept()


def _readonly_line_edit() -> QLineEdit:
    editor = QLineEdit()
    editor.setReadOnly(True)
    return editor


def _hex(value: str, fallback: str) -> str:
    text = (value or "").strip()
    if len(text) == 7 and text.startswith("#"):
        return text.lower()
    return fallback
