"""Qt 新建 / 编辑项目对话框。

字段与 Tk 版一致：项目名称（必填）、项目日期（无时间 / 单个时间 / 起止时间）、
项目状态、项目描述。保存走 project_manager.create_project / update_project；
编辑模式校验失败或落盘失败时不覆盖原项目（对话框保持打开，仅提示）。
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
    QPlainTextEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from ....project_manager import create_project, update_project
from ....project_status import ProjectStatus
from ...font_manager import font_manager

DATE_TYPES = ["无时间", "单个时间", "起止时间"]

_STATUS_OPTIONS = [
    (ProjectStatus.EDITING.display_name, ProjectStatus.EDITING),
    (ProjectStatus.DONE.display_name, ProjectStatus.DONE),
]


def _parse_date(text: str) -> QDate:
    qd = QDate.fromString((text or "").strip(), "yyyy-MM-dd")
    return qd if qd.isValid() else QDate.currentDate()


def _date_text(edit: QDateEdit) -> str:
    return edit.date().toString("yyyy-MM-dd")


class NewProjectDialog(QDialog):
    def __init__(self, parent=None, on_done=None, mode="new", project_data=None):
        super().__init__(parent)
        self.on_done = on_done
        self.mode = mode
        self.project_data = project_data or {}

        self.setWindowTitle("编辑项目" if mode == "edit" else "新建项目")
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

        # ── 项目名称（必填）──
        self.name_edit = QLineEdit(self.project_data.get("name", ""))
        self.name_edit.setPlaceholderText("如：XX小区装修")
        form.addRow("项目名称", self.name_edit)

        # ── 项目日期：三态（无时间 / 单个时间 / 起止时间）──
        date_box = QWidget()
        date_col = QVBoxLayout(date_box)
        date_col.setContentsMargins(0, 0, 0, 0)
        date_col.setSpacing(6)
        self.date_type_cb = QComboBox()
        self.date_type_cb.addItems(DATE_TYPES)
        date_col.addWidget(self.date_type_cb)

        self._single_edit = QDateEdit()
        self._single_edit.setCalendarPopup(True)
        self._single_edit.setDisplayFormat("yyyy-MM-dd")
        date_col.addWidget(self._single_edit)

        self._range_widget = QWidget()
        range_row = QHBoxLayout(self._range_widget)
        range_row.setContentsMargins(0, 0, 0, 0)
        range_row.setSpacing(8)
        range_row.addWidget(QLabel("起"))
        self._start_edit = QDateEdit()
        self._start_edit.setCalendarPopup(True)
        self._start_edit.setDisplayFormat("yyyy-MM-dd")
        range_row.addWidget(self._start_edit, 1)
        range_row.addWidget(QLabel("止"))
        self._end_edit = QDateEdit()
        self._end_edit.setCalendarPopup(True)
        self._end_edit.setDisplayFormat("yyyy-MM-dd")
        range_row.addWidget(self._end_edit, 1)
        date_col.addWidget(self._range_widget)
        form.addRow("项目日期", date_box)

        # ── 项目状态 ──
        self.status_cb = QComboBox()
        for text, status in _STATUS_OPTIONS:
            self.status_cb.addItem(text, status)
        form.addRow("项目状态", self.status_cb)

        # ── 项目描述（可选）──
        self.desc_edit = QPlainTextEdit()
        self.desc_edit.setPlaceholderText("输入项目简介，默认为空")
        self.desc_edit.setFixedHeight(72)
        form.addRow("项目描述", self.desc_edit)

        layout.addLayout(form)

        # ── 初始值 ──
        default_start = self.project_data.get("project_date_start", "") or ""
        default_end = self.project_data.get("project_date_end", "") or ""
        if mode == "new" and not default_start:
            default_start = datetime.now().strftime("%Y-%m-%d")
        initial_type = (
            self.project_data.get("project_date_type", "")
            if mode == "edit"
            else "单个时间"
        )
        if initial_type not in DATE_TYPES:
            initial_type = "无时间"
        self.date_type_cb.setCurrentText(initial_type)
        self._single_edit.setDate(_parse_date(default_start))
        self._start_edit.setDate(_parse_date(default_start))
        self._end_edit.setDate(_parse_date(default_end))
        status = ProjectStatus.from_value(
            self.project_data.get("status", ProjectStatus.EDITING.value)
        )
        self.status_cb.setCurrentIndex(max(self.status_cb.findData(status), 0))
        self.desc_edit.setPlainText(self.project_data.get("description", "") or "")
        self.date_type_cb.currentTextChanged.connect(self._sync_date_visibility)
        self._sync_date_visibility()

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

        self.name_edit.setFocus()

    def _sync_date_visibility(self) -> None:
        date_type = self.date_type_cb.currentText()
        self._single_edit.setVisible(date_type == "单个时间")
        self._range_widget.setVisible(date_type == "起止时间")

    def _confirm(self) -> None:
        name = self.name_edit.text().strip()
        if not name:
            QMessageBox.warning(self, "提示", "请输入项目名称")
            return

        desc = self.desc_edit.toPlainText().strip()
        date_type = self.date_type_cb.currentText()
        date_start = date_end = ""
        if date_type == "单个时间":
            date_start = _date_text(self._single_edit)
        elif date_type == "起止时间":
            date_start = _date_text(self._start_edit)
            date_end = _date_text(self._end_edit)
        status = self.status_cb.currentData() or ProjectStatus.EDITING
        status = ProjectStatus.from_value(status)

        try:
            if self.mode == "edit":
                pd = self.project_data
                pd["name"] = name
                pd["description"] = desc
                pd["project_date_type"] = date_type
                pd["project_date_start"] = date_start
                pd["project_date_end"] = date_end
                pd["status"] = status.value
                update_project(pd.get("project_uuid", ""), pd)
            else:
                create_project(
                    name,
                    description=desc,
                    project_date_type=date_type,
                    project_date_start=date_start,
                    project_date_end=date_end,
                    status=status,
                )
        except Exception as exc:
            QMessageBox.critical(self, "保存失败", f"无法保存项目：{exc}")
            return

        self.accept()
        if self.on_done:
            self.on_done()
