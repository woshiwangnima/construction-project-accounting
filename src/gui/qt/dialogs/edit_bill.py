"""Qt 编辑 / 添加账单记录对话框。

字段与 Tk 版一致：工作内容关联（支持「不关联（孤儿）」）、计算公式（符号面板 +
标准化展示 / 结果 / 金额预览）、备注、日期三态（无时间 / 单个时间 / 起止时间）。

保存不直接写项目：构建更新后的 bill dict 后调用 on_saved(updated_bill)，由调用方
写回 bills 并落盘。孤儿逻辑与 Tk 版 / paste_actions 一致：
- 从关联切换为孤儿：对原工种做 frozen_snapshot / frozen_total 冻结并标记需要关注；
- 从孤儿重新关联：清掉 frozen_snapshot / frozen_total / _needs_attention；
- 孤儿保持孤儿：保留原有 frozen 数据。
"""

from datetime import datetime

from PySide6.QtCore import QDate, Qt
from PySide6.QtWidgets import (
    QComboBox,
    QDateEdit,
    QDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from ....billing import read_billing
from ....bill_recompute import recompute_bill_total
from ....bill_review import is_bill_reviewed
from ....billing_resolver import is_orphan, resolve_trade_item
from ....calculator import (
    MathParseError,
    evaluate_canonical,
    to_canonical,
    to_display,
)
from ....trade_item_id import ensure_trade_item_id
from ...font_manager import font_manager
from ...theme import DANGER, TEXT_SECONDARY

DATE_TYPES = ["无时间", "单个时间", "起止时间"]
ORPHAN_LABEL = "不关联（孤儿）"
ORPHAN_HINT = "不关联（孤儿）：账单脱离工作项目，保留最后已知金额与单价快照。"

_FORMULA_SYMBOLS = ("×", "÷", "+", "-", "(", ")")
_FORMULA_CTRL = ("清空", "删除")


def _format_number(value: float) -> str:
    text = f"{value:.10f}".rstrip("0").rstrip(".")
    return text or "0"


def _formula_result_text(content: str, op_map: dict) -> str:
    content = (content or "").strip()
    if not content:
        return ""
    try:
        value = evaluate_canonical(to_canonical(content, op_map))
    except MathParseError:
        return "结果：错误"
    return f"结果：{_format_number(value)}"


def _display_or_error(content: str, op_map: dict) -> tuple[str, str | None]:
    """返回 (标准化展示公式, 解析错误)。空公式返回 ("", None)。"""
    content = (content or "").strip()
    if not content:
        return "", None
    try:
        return to_display(to_canonical(content, op_map)), None
    except MathParseError as exc:
        return "", str(exc)


def _parse_date(text: str) -> QDate:
    qd = QDate.fromString((text or "").strip(), "yyyy-MM-dd")
    return qd if qd.isValid() else QDate.currentDate()


def _date_text(edit: QDateEdit) -> str:
    return edit.date().toString("yyyy-MM-dd")


def _make_date_edit() -> QDateEdit:
    edit = QDateEdit()
    edit.setCalendarPopup(True)
    edit.setDisplayFormat("yyyy-MM-dd")
    return edit


class EditBillDialog(QDialog):
    def __init__(self, parent, bill, project_data, op_map, on_saved):
        super().__init__(parent)
        self._bill = bill or {}
        self._project_data = project_data or {}
        self._trade_items = self._project_data.get("trade_items", []) or []
        self._op_map = op_map or {}
        self.on_saved = on_saved
        self._item_labels: list[str] = []

        self.setWindowTitle("编辑记录" if self._bill.get("id") else "添加记录")
        self.setModal(True)
        self.setMinimumWidth(480)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 16, 20, 16)
        layout.setSpacing(12)

        title = QLabel(self.windowTitle())
        title.setFont(font_manager.get("heading"))
        layout.addWidget(title)

        # ── 工作内容关联 ──
        layout.addWidget(self._section_label("选择工作项目"))
        form = QFormLayout()
        form.setSpacing(10)
        form.setLabelAlignment(Qt.AlignLeft)

        self._trade_combo = QComboBox()
        self._trade_combo.addItem(ORPHAN_LABEL)
        for ti in self._trade_items:
            label = f"{ti.get('category', '')} - {ti.get('name', '')}"
            self._item_labels.append(label)
            self._trade_combo.addItem(label)
        form.addRow("工作内容", self._trade_combo)
        layout.addLayout(form)

        self._orphan_hint = QLabel(ORPHAN_HINT)
        self._orphan_hint.setWordWrap(True)
        self._orphan_hint.setStyleSheet(f"color: {DANGER};")
        layout.addWidget(self._orphan_hint)

        self._info_lbl = QLabel("")
        self._info_lbl.setStyleSheet(f"color: {TEXT_SECONDARY};")
        layout.addWidget(self._info_lbl)

        # ── 计算公式 ──
        layout.addWidget(self._section_label("输入计算公式"))
        self._content_edit = QLineEdit()
        self._content_edit.setPlaceholderText("如：3×4+2")
        layout.addWidget(self._content_edit)

        sym_row = QHBoxLayout()
        sym_row.setSpacing(6)
        for sym in _FORMULA_SYMBOLS:
            btn = QPushButton(sym)
            btn.setProperty("flat", True)
            btn.clicked.connect(lambda _=False, s=sym: self._insert_symbol(s))
            sym_row.addWidget(btn)
        clear_btn = QPushButton("清空")
        clear_btn.setProperty("secondary", True)
        clear_btn.clicked.connect(self._clear_formula)
        del_btn = QPushButton("删除")
        del_btn.setProperty("secondary", True)
        del_btn.clicked.connect(self._backspace)
        sym_row.addStretch(1)
        sym_row.addWidget(clear_btn)
        sym_row.addWidget(del_btn)
        layout.addLayout(sym_row)

        self._display_lbl = QLabel("")
        self._display_lbl.setWordWrap(True)
        layout.addWidget(self._display_lbl)

        amount_row = QHBoxLayout()
        amount_row.setSpacing(12)
        amount_lbl = QLabel("金额")
        amount_lbl.setStyleSheet(f"color: {DANGER}; font-weight: bold;")
        self._amount_lbl = QLabel("")
        self._amount_lbl.setFont(font_manager.get("heading"))
        self._amount_lbl.setStyleSheet(f"color: {DANGER};")
        amount_row.addWidget(amount_lbl)
        amount_row.addWidget(self._amount_lbl)
        amount_row.addStretch(1)
        self._result_lbl = QLabel("")
        self._result_lbl.setStyleSheet(f"color: {TEXT_SECONDARY};")
        amount_row.addWidget(self._result_lbl)
        layout.addLayout(amount_row)

        # ── 备注 ──
        layout.addWidget(self._section_label("备注（可选）"))
        self._note_edit = QLineEdit(self._bill.get("note", ""))
        layout.addWidget(self._note_edit)

        # ── 日期三态 ──
        layout.addWidget(self._section_label("日期"))
        date_box = QWidget()
        date_col = QVBoxLayout(date_box)
        date_col.setContentsMargins(0, 0, 0, 0)
        date_col.setSpacing(6)
        self._date_type_cb = QComboBox()
        self._date_type_cb.addItems(DATE_TYPES)
        date_col.addWidget(self._date_type_cb)

        self._single_edit = _make_date_edit()
        date_col.addWidget(self._single_edit)

        self._range_widget = QWidget()
        range_row = QHBoxLayout(self._range_widget)
        range_row.setContentsMargins(0, 0, 0, 0)
        range_row.setSpacing(8)
        range_row.addWidget(QLabel("起"))
        self._start_edit = _make_date_edit()
        range_row.addWidget(self._start_edit, 1)
        range_row.addWidget(QLabel("止"))
        self._end_edit = _make_date_edit()
        range_row.addWidget(self._end_edit, 1)
        date_col.addWidget(self._range_widget)
        layout.addWidget(date_box)

        # ── 底部按钮：取消（次） / 保存（主）──
        btns = QHBoxLayout()
        btns.addStretch(1)
        cancel = QPushButton("取消")
        cancel.setProperty("secondary", True)
        cancel.clicked.connect(self.reject)
        save = QPushButton("保存")
        save.setDefault(True)
        save.clicked.connect(self._confirm)
        btns.addWidget(cancel)
        btns.addWidget(save)
        layout.addLayout(btns)

        # ── 初始值 ──
        default_start = self._bill.get("work_date_start", "") or ""
        default_end = self._bill.get("work_date_end", "") or ""
        default_type = self._bill.get("work_date_type", "") or (
            "单个时间" if default_start else "无时间"
        )
        if default_type not in DATE_TYPES:
            default_type = "无时间"
        self._date_type_cb.setCurrentText(default_type)
        self._single_edit.setDate(_parse_date(default_start))
        self._start_edit.setDate(_parse_date(default_start))
        self._end_edit.setDate(_parse_date(default_end))
        self._date_type_cb.currentTextChanged.connect(self._sync_date_visibility)
        self._sync_date_visibility()

        self._content_edit.setText(self._bill.get("content", ""))
        self._preselect_trade_item()

        self._trade_combo.currentIndexChanged.connect(self._on_trade_changed)
        self._content_edit.textChanged.connect(self._refresh_preview)
        self._on_trade_changed()
        self._refresh_preview()

    # ── UI 辅助 ──────────────────────────────────────────────────────────────

    def _section_label(self, text: str) -> QLabel:
        label = QLabel(text)
        label.setStyleSheet("font-weight: bold;")
        return label

    def _sync_date_visibility(self) -> None:
        date_type = self._date_type_cb.currentText()
        self._single_edit.setVisible(date_type == "单个时间")
        self._range_widget.setVisible(date_type == "起止时间")

    def _preselect_trade_item(self) -> None:
        pre_ti = resolve_trade_item(self._bill, self._trade_items)
        if pre_ti is not None:
            label = f"{pre_ti.get('category', '')} - {pre_ti.get('name', '')}"
            idx = self._trade_combo.findText(label)
            if idx >= 0:
                self._trade_combo.setCurrentIndex(idx)
            return
        self._trade_combo.setCurrentIndex(0)

    def _selected_item(self):
        selected = self._trade_combo.currentText().strip()
        if selected == ORPHAN_LABEL:
            return None
        for ti, label in zip(self._trade_items, self._item_labels):
            if label == selected:
                return ti
        return None

    def _on_trade_changed(self) -> None:
        self._orphan_hint.setVisible(
            self._trade_combo.currentText() == ORPHAN_LABEL
        )
        self._refresh_preview()

    # ── 公式输入面板 ─────────────────────────────────────────────────────────

    def _insert_symbol(self, sym: str) -> None:
        edit = self._content_edit
        pos = edit.cursorPosition()
        text = edit.text()
        edit.setText(text[:pos] + sym + text[pos:])
        edit.setCursorPosition(pos + len(sym))
        edit.setFocus()

    def _clear_formula(self) -> None:
        self._content_edit.clear()
        self._content_edit.setFocus()

    def _backspace(self) -> None:
        edit = self._content_edit
        pos = edit.cursorPosition()
        if pos <= 0:
            return
        text = edit.text()
        edit.setText(text[: pos - 1] + text[pos:])
        edit.setCursorPosition(pos - 1)
        edit.setFocus()

    # ── 实时预览（标准化公式 / 结果 / 金额）──────────────────────────────────

    def _refresh_preview(self) -> None:
        content = self._content_edit.text().strip()
        display_text, parse_error = _display_or_error(content, self._op_map)
        ti = self._selected_item()

        if parse_error:
            self._display_lbl.setText(f"公式错误：{parse_error}")
            self._result_lbl.setText(_formula_result_text(content, self._op_map))
            self._amount_lbl.setText("请输入有效算式")
            return

        self._display_lbl.setText(display_text)
        self._result_lbl.setText(_formula_result_text(content, self._op_map))

        if ti is None:
            self._info_lbl.setText("")
            self._amount_lbl.setText("")
            return

        billing = read_billing(ti)
        if billing.is_per_unit:
            self._info_lbl.setText(
                f"类别：{ti.get('category', '')}　　单价：{billing.unit_price:.2f} {billing.unit}"
            )
        else:
            self._info_lbl.setText(f"类别：{ti.get('category', '')}　　无单价计费")

        if not content:
            self._amount_lbl.setText("")
            return
        try:
            result = evaluate_canonical(to_canonical(content, self._op_map))
        except MathParseError:
            self._amount_lbl.setText("请输入有效算式")
            return
        if billing.is_per_unit:
            total = round(result * billing.unit_price, 2)
        else:
            total = round(result, 2)
        self._amount_lbl.setText(f"￥{total:.2f}")

    # ── 保存 ─────────────────────────────────────────────────────────────────

    def _confirm(self) -> None:
        selected = self._trade_combo.currentText().strip()
        if not selected:
            QMessageBox.warning(self, "提示", "请选择工作项目")
            return
        content_raw = self._content_edit.text().strip()
        if not content_raw:
            QMessageBox.warning(self, "提示", "请输入计算公式")
            return
        try:
            canonical = to_canonical(content_raw, self._op_map)
            evaluate_canonical(canonical)
        except MathParseError as exc:
            QMessageBox.warning(self, "公式错误", f"无法解析公式：\n{exc}")
            return

        existing = self._bill or {}
        is_new = not existing.get("id")
        ti = self._selected_item()
        if ti is None and is_new:
            QMessageBox.warning(self, "提示", "请选择工作项目")
            return

        date_type = self._date_type_cb.currentText()
        date_start = date_end = ""
        if date_type == "单个时间":
            date_start = _date_text(self._single_edit)
        elif date_type == "起止时间":
            date_start = _date_text(self._start_edit)
            date_end = _date_text(self._end_edit)

        updated: dict = {
            "content": content_raw,
            "note": self._note_edit.text().strip(),
            "work_date_type": date_type,
            "work_date_start": date_start,
            "work_date_end": date_end,
            "record_time": existing.get("record_time")
            or datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        }
        if existing.get("id"):
            updated["id"] = existing["id"]
        if is_bill_reviewed(existing):
            updated["reviewed"] = True

        self._apply_trade_association(updated, existing, ti)

        if self.on_saved:
            self.on_saved(updated)
        self.accept()

    def _apply_trade_association(self, updated: dict, existing: dict, ti) -> None:
        """按工作内容选择结果填写 trade_item_id 与 frozen_* 字段（与 Tk 一致）。"""
        old_tid = existing.get("trade_item_id", "")
        was_orphan = is_orphan(existing, self._trade_items)

        if ti is None:
            # 切换 / 保持为孤儿
            updated["trade_item_id"] = ""
            if was_orphan:
                for key in ("frozen_snapshot", "frozen_total", "_needs_attention"):
                    value = existing.get(key)
                    if value is not None:
                        updated[key] = value
            else:
                abandoned = resolve_trade_item(existing, self._trade_items)
                if abandoned is not None:
                    billing = read_billing(abandoned)
                    updated["frozen_snapshot"] = {
                        "name": abandoned.get("name", ""),
                        "category": abandoned.get("category", ""),
                        "has_unit": billing.has_unit,
                        "unit_price": billing.unit_price,
                        "unit": billing.unit,
                    }
                    updated["frozen_total"] = recompute_bill_total(
                        {**updated, "trade_item_id": old_tid},
                        self._trade_items,
                        self._op_map,
                    )
                    updated["_needs_attention"] = True
            return

        # 关联 / 重新关联：清掉孤儿冻结数据
        updated["trade_item_id"] = ensure_trade_item_id(ti)
        if was_orphan:
            updated.pop("frozen_snapshot", None)
            updated.pop("frozen_total", None)
            updated.pop("_needs_attention", None)
