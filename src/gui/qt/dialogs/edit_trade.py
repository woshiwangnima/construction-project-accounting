"""Qt 编辑 / 添加工作项目对话框。

字段与 Tk 版一致：工作类型（分类）、工作名称（必填）、计费类型
（按单价 / 无单价，切换时禁用单价 + 单位）、单价、单位。
保存把名称 / 分类 / 计费三件套写回 item 的 billing 字段
（billing.read_billing / write_billing 的字段名：has_unit / unit_price / unit），
并确保 item 具备稳定 id（ensure_trade_item_id），完成后回调 on_saved(item)。
"""

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
)

from ....billing import Billing, read_billing, write_billing
from ....trade_item_id import ensure_trade_item_id
from ...font_manager import font_manager
from ...theme import TEXT_SECONDARY

BILLING_TYPES = ["按单价", "无单价"]


class EditTradeItemDialog(QDialog):
    def __init__(self, parent, trade_item, categories, op_map, on_saved):
        super().__init__(parent)
        self.item = trade_item or {}
        self._op_map = op_map or {}
        self.on_saved = on_saved

        self.setWindowTitle("编辑工作项目")
        self.setModal(True)
        self.setMinimumWidth(480)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 16, 20, 16)
        layout.setSpacing(12)

        title = QLabel(self.windowTitle())
        title.setFont(font_manager.get("heading"))
        layout.addWidget(title)

        form = QFormLayout()
        form.setSpacing(10)
        form.setLabelAlignment(Qt.AlignLeft)

        # ── 工作类型（分类）──
        self.cat_cb = QComboBox()
        self.cat_cb.addItems([str(c) for c in (categories or [])])
        current_cat = self.item.get("category", "")
        if current_cat:
            idx = self.cat_cb.findText(current_cat)
            if idx >= 0:
                self.cat_cb.setCurrentIndex(idx)
        elif categories:
            self.cat_cb.setCurrentIndex(0)
        form.addRow("工作类型", self.cat_cb)

        # ── 工作名称（必填）──
        self.name_edit = QLineEdit(self.item.get("name", ""))
        self.name_edit.setPlaceholderText("如：拆除隔断墙")
        form.addRow("工作名称", self.name_edit)

        # ── 计费类型 ──
        billing = read_billing(self.item)
        self.billing_cb = QComboBox()
        self.billing_cb.addItems(BILLING_TYPES)
        self.billing_cb.setCurrentText(
            "按单价" if billing.is_per_unit else "无单价"
        )
        form.addRow("计费类型", self.billing_cb)

        # ── 单价 + 单位（按单价时可用）──
        price_row = QHBoxLayout()
        price_row.setSpacing(8)
        default_price = 1
        if self.item.get("name"):
            default_price = billing.unit_price
        self.price_edit = QLineEdit(str(default_price))
        self.price_edit.setPlaceholderText("如：50")
        price_row.addWidget(self.price_edit, 1)
        price_row.addWidget(QLabel("元 /"), 0)
        self.unit_edit = QLineEdit(billing.unit)
        self.unit_edit.setPlaceholderText("单位（如：m²）")
        price_row.addWidget(self.unit_edit, 1)
        form.addRow("单价 / 单位", price_row)

        layout.addLayout(form)

        hint = QLabel("无单价计费：账单按公式结果直接计金额，不乘单价。")
        hint.setStyleSheet(f"color: {TEXT_SECONDARY};")
        layout.addWidget(hint)

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

        self.billing_cb.currentIndexChanged.connect(self._toggle_price)
        self._toggle_price()

    def _toggle_price(self) -> None:
        per_unit = self.billing_cb.currentText() == "按单价"
        self.price_edit.setEnabled(per_unit)
        self.unit_edit.setEnabled(per_unit)

    def _confirm(self) -> None:
        name = self.name_edit.text().strip()
        if not name:
            QMessageBox.warning(self, "提示", "请输入工作名称")
            return

        is_per_unit = self.billing_cb.currentText() == "按单价"
        price = 1
        unit = ""
        if is_per_unit:
            try:
                price = float(self.price_edit.text().strip())
            except ValueError:
                QMessageBox.warning(self, "提示", "单价请输入数字")
                return
            unit = self.unit_edit.text().strip()
            if not unit:
                QMessageBox.warning(self, "提示", "请输入或选择单位")
                return

        self.item["category"] = self.cat_cb.currentText()
        ensure_trade_item_id(self.item)
        self.item["name"] = name
        write_billing(self.item, Billing(
            has_unit=is_per_unit,
            unit_price=price,
            unit=unit,
        ))

        if self.on_saved:
            self.on_saved(self.item)
        self.accept()
