"""Qt 侧栏（替代 Tk Sidebar）。

P2 范围：新建/导入/导出/设置按钮、搜索过滤、项目列表 + 选中防抖、
右键菜单（置顶/打开位置可用；编辑/回滚/删除 P4 接入对话框，暂为占位提示）。
"""
import os
import subprocess
import sys

from qtawesome import icon as qta_icon
from PySide6.QtGui import QColor
from PySide6.QtCore import QSize, Qt, QTimer, Signal
from PySide6.QtWidgets import (
    QBoxLayout, QHBoxLayout, QLabel, QLineEdit, QListWidget, QListWidgetItem,
    QMenu, QMessageBox, QPushButton, QToolButton, QVBoxLayout, QWidget,
)

from ...logger import logger
from ...project_manager import list_projects, project_file_path, toggle_pin
from ...project_status import ProjectStatus
from .. import shortcut_manager as sm_module
from ..font_manager import font_manager
from ..theme import (
    ACCENT, ACCENT_HOVER, ACCENT_PRESSED, APP_BG, HIGHLIGHT_BG, INFO_BG, SIDEBAR_BG, SIDEBAR_FG,
    SIDEBAR_HOVER, SIDEBAR_ITEM_BORDER, STATUS_DONE_FG, STATUS_EDITING_FG, SUCCESS_BG,
    TEXT_PRIMARY, TEXT_SECONDARY, TEXT_TERTIARY,
)

sm = sm_module.shortcut_manager


class ProjectRow(QWidget):
    """项目列表行：指示条 + 名称 + 状态 pill（水平排布）。"""

    def __init__(self, name: str, status: ProjectStatus | None, parent=None):
        super().__init__(parent)
        self.setObjectName("project_row")
        self._selected = False
        self.setStyleSheet("QWidget#project_row { background: transparent; border-radius: 8px; } QLabel { background: transparent; border: none; }")
        layout = QHBoxLayout(self)
        layout.setContentsMargins(10, 8, 10, 8)
        layout.setSpacing(10)
        self._indicator = QLabel(self)
        self._indicator.setFixedWidth(4)
        self._indicator.setFixedHeight(18)
        layout.addWidget(self._indicator)
        self._name_lbl = QLabel(name)
        self._name_lbl.setTextInteractionFlags(Qt.NoTextInteraction)
        self._status_lbl = QLabel("")
        layout.addWidget(self._name_lbl, 1)
        layout.addWidget(self._status_lbl)
        self.set_status(status)
        self._apply_style()

    def sizeHint(self):
        sz = super().sizeHint()
        return QSize(sz.width(), max(44, sz.height()))

    def _apply_style(self) -> None:
        if self._selected:
            self._name_lbl.setFont(font_manager.get("entry_item"))
            self.setStyleSheet(
                f"QWidget#project_row {{ background: #ebf5ff; border-radius: 8px; border: none; }}"
                f"QLabel {{ background: transparent; border: none; }}"
            )
            self._name_lbl.setStyleSheet(f"color: {ACCENT}; font-weight: bold; background: transparent; border: none;")
            self._indicator.setStyleSheet(
                f"background: {ACCENT}; border-radius: 2px;"
            )
        else:
            self._name_lbl.setFont(font_manager.get("body"))
            self.setStyleSheet(
                f"QWidget#project_row {{ background: transparent; border-radius: 8px; border: none; }}"
                f"QLabel {{ background: transparent; border: none; }}"
            )
            self._name_lbl.setStyleSheet(f"color: {TEXT_PRIMARY}; font-weight: 500; background: transparent; border: none;")
            self._indicator.setStyleSheet("background: transparent;")

    def set_selected(self, selected: bool) -> None:
        """行选中态：浅蓝底 + 左侧蓝色指示条 + ACCENT 名称。"""
        if selected == self._selected:
            return
        self._selected = selected
        self._apply_style()

    def set_status(self, status: ProjectStatus | None) -> None:
        if status is None:
            self._status_lbl.setText("")
            self._status_lbl.setStyleSheet("background: transparent;")
            return
        if status == ProjectStatus.EDITING:
            fg, bg = STATUS_EDITING_FG, INFO_BG
        else:
            fg, bg = STATUS_DONE_FG, SUCCESS_BG
        self._status_lbl.setText(status.display_name)
        self._status_lbl.setStyleSheet(
            f"color: {fg}; background: {bg}; border: none; border-radius: 10px;"
            f" padding: 3px 10px; font-size: 12px; font-weight: bold;"
        )

    def set_name(self, name: str) -> None:
        if self._name_lbl.toolTip():
            self._name_lbl.setToolTip(name)
            self._name_lbl.setText(name[:1] if name else "?")
        else:
            self._name_lbl.setText(name)

    def set_compact(self, compact: bool) -> None:
        """紧凑侧栏只保留项目首字母，完整名称通过工具提示提供。"""
        if compact:
            name = self._name_lbl.text().strip()
            self._name_lbl.setText(name[:1] if name else "?")
            self._name_lbl.setToolTip(name)
            self._name_lbl.setAlignment(Qt.AlignCenter)
            self._indicator.hide()
            self._status_lbl.hide()
        else:
            self._name_lbl.setText(self._name_lbl.toolTip() or self._name_lbl.text())
            self._name_lbl.setToolTip("")
            self._name_lbl.setAlignment(Qt.AlignVCenter | Qt.AlignLeft)
            self._indicator.show()
            self._status_lbl.show()
        self._apply_style()


class QtSidebar(QWidget):
    compact_toggled = Signal(bool)

    def __init__(self, on_select, editability=None, on_settings_closed=None,
                 on_app_close=None):
        super().__init__()
        self.on_select = on_select
        self.selected_uuid = None
        self._editability = editability
        self._on_settings_closed = on_settings_closed
        self._on_app_close = on_app_close
        self._filter_timer = QTimer(self)
        self._filter_timer.setSingleShot(True)
        self._filter_timer.setInterval(150)
        self._filter_timer.timeout.connect(self._flush_filter)
        self._selection_timer = QTimer(self)
        self._selection_timer.setSingleShot(True)
        self._selection_timer.setInterval(120)
        self._selection_timer.timeout.connect(self._flush_selection)
        self._pending_selection_uuid = None
        self._item_widgets: dict[str, ProjectRow] = {}
        self._compact = False
        self._new_btn = None
        self._collapse_btn = None
        self._io_row = None
        self._io_buttons = ()
        self._settings_btn = None
        self._build_ui()
        self.refresh()

    def _build_ui(self) -> None:
        self.setObjectName("sidebar")
        self.setStyleSheet(
            f"QWidget#sidebar {{ background: {SIDEBAR_BG}; color: {SIDEBAR_FG}; }}"
        )
        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 12, 14, 12)
        layout.setSpacing(10)

        top_row = QWidget()
        top_layout = QHBoxLayout(top_row)
        top_layout.setContentsMargins(0, 0, 0, 0)
        top_layout.setSpacing(8)

        new_btn = QPushButton(" + 新建工程项目 ")
        new_btn.setIcon(qta_icon("fa5s.plus-circle"))
        new_btn.setIconSize(QSize(18, 18))
        new_btn.setStyleSheet(
            f"QPushButton {{ background: {ACCENT}; color: #ffffff; border: none; border-radius: 8px;"
            f" padding: 10px 16px; font-weight: bold; font-size: 15px; min-height: 28px; }}"
            f"QPushButton:hover {{ background: {ACCENT_HOVER}; }}"
            f"QPushButton:pressed {{ background: {ACCENT_PRESSED}; }}"
        )
        new_btn.clicked.connect(self._new_project)
        new_btn.setToolTip("创建新的记账项目")
        self._new_btn = new_btn
        top_layout.addWidget(new_btn, 1)

        collapse_btn = QToolButton()
        collapse_btn.setIcon(qta_icon("fa5s.angle-double-left"))
        collapse_btn.setIconSize(QSize(16, 16))
        collapse_btn.setToolTip("收起/展开侧边栏（Ctrl+B）")
        collapse_btn.setAutoRaise(True)
        collapse_btn.setStyleSheet(
            f"QToolButton {{ border-radius: 8px; padding: 6px; background: transparent; }}"
            f"QToolButton:hover {{ background: {SIDEBAR_HOVER}; }}"
        )
        collapse_btn.clicked.connect(self.toggle_compact)
        self._collapse_btn = collapse_btn
        top_layout.addWidget(collapse_btn)
        layout.addWidget(top_row)

        io_row = QWidget()
        io_layout = QHBoxLayout(io_row)
        io_layout.setContentsMargins(0, 0, 0, 0)
        io_layout.setSpacing(8)
        import_btn = QPushButton(" 📥 导入工程")
        export_btn = QPushButton(" 📤 导出工程")
        for _b in (import_btn, export_btn):
            _b.setIconSize(QSize(14, 14))
            _b.setStyleSheet(
                "QPushButton { background: #ffffff; color: #374151; border: 1px solid #d1d5db;"
                " border-radius: 8px; padding: 8px 12px; font-weight: bold; font-size: 14px; min-height: 24px; }"
                "QPushButton:hover { background: #f3f4f6; color: #111827; border-color: #9ca3af; }"
            )
        import_btn.clicked.connect(self._import_project)
        export_btn.clicked.connect(self._export_project)
        io_layout.addWidget(import_btn, 1)
        io_layout.addWidget(export_btn, 1)
        self._io_row = io_row
        self._io_buttons = (import_btn, export_btn)
        layout.addWidget(io_row)

        self.search_edit = QLineEdit()
        self.search_edit.setPlaceholderText("🔍 查找工程项目...")
        self.search_edit.setClearButtonEnabled(True)
        self.search_edit.setStyleSheet(
            "QLineEdit { background: #ffffff; color: #1f2937; border: 1px solid #d1d5db; border-radius: 8px; padding: 8px 12px; font-size: 14px; min-height: 24px; }"
            "QLineEdit:focus { border-color: #007aff; background: #ffffff; }"
        )
        self.search_edit.textChanged.connect(self._schedule_filter)
        layout.addWidget(self.search_edit)

        self.list_widget = QListWidget()
        self.list_widget.setSelectionMode(QListWidget.SingleSelection)
        self.list_widget.setContextMenuPolicy(Qt.CustomContextMenu)
        self.list_widget.customContextMenuRequested.connect(self._on_context_menu)
        self.list_widget.currentItemChanged.connect(self._on_current_item_changed)
        layout.addWidget(self.list_widget, 1)

        settings_btn = QPushButton(" ⚙️ 软件系统设置")
        settings_btn.setIconSize(QSize(16, 16))
        settings_btn.setStyleSheet(
            "QPushButton { background: #ffffff; color: #374151; border: 1px solid #d1d5db;"
            " border-radius: 8px; padding: 9px 14px; font-weight: bold; font-size: 14px; min-height: 26px; }"
            "QPushButton:hover { background: #f3f4f6; color: #111827; border-color: #9ca3af; }"
        )
        settings_btn.clicked.connect(self._open_settings)
        settings_btn.setToolTip("修改软件配置与字号")
        self._settings_btn = settings_btn
        layout.addWidget(settings_btn)

    def toggle_compact(self) -> None:
        self.set_compact(not self._compact)

    def set_compact(self, compact: bool) -> None:
        compact = bool(compact)
        if compact == self._compact:
            return
        self._compact = compact
        self._new_btn.setText("") if compact else self._new_btn.setText("新建项目")
        self._new_btn.setToolTip("新建项目")
        self._collapse_btn.setIcon(
            qta_icon("fa5s.angle-double-right" if compact else "fa5s.angle-double-left")
        )
        self._collapse_btn.setToolTip(
            "展开侧栏（Ctrl+B）" if compact else "收起侧栏（Ctrl+B）"
        )

        self._io_row.setVisible(not compact)
        self.search_edit.setVisible(not compact)
        self._settings_btn.setText("") if compact else self._settings_btn.setText("设置")
        self._settings_btn.setToolTip("设置")
        for row in self._item_widgets.values():
            row.set_compact(compact)

        self._compact = compact
        self.compact_toggled.emit(compact)

    # ── 数据刷新 ────────────────────────────────────────────────────────────

    def refresh(self) -> None:
        prev_selected = self.selected_uuid
        self.list_widget.blockSignals(True)
        try:
            self.list_widget.clear()
            self._item_widgets = {}
            projects = list_projects()
            query = self.search_edit.text().strip().lower()
            filtered = [p for p in projects if not query or query in p.get("name", "").lower()]
            for p in filtered:
                self._add_item(p)
            if not filtered:
                empty = QListWidgetItem("暂无项目\n点击上方按钮创建")
                empty.setForeground(QColor(TEXT_TERTIARY))
                empty.setTextAlignment(Qt.AlignCenter)
                empty.setFont(font_manager.get("small"))
                self.list_widget.addItem(empty)
            self._set_selected(prev_selected if prev_selected in self._item_widgets else None)
            self._update_row_selection(self.selected_uuid)
        finally:
            self.list_widget.blockSignals(False)

    def select_project(self, uuid: str | None, notify: bool = True) -> None:
        """显式选中并可选地通知主区域加载项目。"""
        self.selected_uuid = uuid
        self._pending_selection_uuid = None
        if self._selection_timer.isActive():
            self._selection_timer.stop()
        for i in range(self.list_widget.count()):
            item = self.list_widget.item(i)
            if self._item_uuid(item) == uuid:
                self.list_widget.blockSignals(True)
                self.list_widget.setCurrentItem(item)
                self.list_widget.blockSignals(False)
                break
        self._update_row_selection(uuid)
        if notify and self.on_select is not None:
            self.on_select(uuid)

    def select_initial_project(self) -> None:
        """启动时优先打开已有项目，避免主区域停留在欢迎页。"""
        if self.selected_uuid or not self._item_widgets:
            return
        first_uuid = next(iter(self._item_widgets))
        self.select_project(first_uuid, notify=True)

    def _add_item(self, project) -> None:
        uuid = project.get("project_uuid") or project.get("uuid")
        if not uuid:
            return
        status = ProjectStatus.from_value(project.get("status"))
        row = ProjectRow(project.get("name", ""), status)
        item = QListWidgetItem()
        item.setData(Qt.UserRole, uuid)
        item.setSizeHint(row.sizeHint())
        self.list_widget.addItem(item)
        self.list_widget.setItemWidget(item, row)
        if self._compact:
            row.set_compact(True)
        self._item_widgets[uuid] = row

    def _item_uuid(self, item: QListWidgetItem | None) -> str | None:
        if item is None:
            return None
        return item.data(Qt.UserRole) or None

    # ── 选中 / 搜索 防抖 ────────────────────────────────────────────────────

    def _on_current_item_changed(self, current, _previous) -> None:
        uuid = self._item_uuid(current)
        self._update_row_selection(uuid)
        if uuid is None:
            return
        self._pending_selection_uuid = uuid
        self._selection_timer.start()

    def _update_row_selection(self, selected_uuid: str | None) -> None:
        """按当前选中 uuid 统一更新所有行的选中视觉（不改变防抖/持久化逻辑）。"""
        for uuid, row in self._item_widgets.items():
            row.set_selected(uuid == selected_uuid)

    def _schedule_filter(self) -> None:
        self._filter_timer.start()

    def _flush_filter(self) -> None:
        self.refresh()

    def _flush_selection(self) -> None:
        uuid = self._pending_selection_uuid
        self._pending_selection_uuid = None
        if uuid is None or uuid == self.selected_uuid:
            return
        self.selected_uuid = uuid
        if self.on_select is not None:
            self.on_select(uuid)

    def _set_selected(self, uuid: str | None) -> None:
        self.selected_uuid = uuid
        for i in range(self.list_widget.count()):
            item = self.list_widget.item(i)
            if self._item_uuid(item) == uuid:
                self.list_widget.setCurrentItem(item)
                break

    # ── 行内容更新（供主窗口回调）───────────────────────────────────────────

    def update_item_name(self, uuid: str, new_name: str) -> None:
        row = self._item_widgets.get(uuid)
        if row is not None:
            row.set_name(new_name)

    def update_item_status(self, uuid: str, status) -> None:
        row = self._item_widgets.get(uuid)
        if row is not None:
            row.set_status(ProjectStatus.from_value(status))

    # ── 右键菜单 ────────────────────────────────────────────────────────────

    def _project_for_menu(self, uuid: str):
        for p in list_projects():
            p_uuid = p.get("project_uuid") if isinstance(p, dict) else getattr(p, "project_uuid", None)
            if p_uuid == uuid:
                return p
        return None

    def _on_context_menu(self, pos) -> None:
        item = self.list_widget.itemAt(pos)
        uuid = self._item_uuid(item)
        if uuid is None:
            return
        self._set_selected(uuid)
        project = self._project_for_menu(uuid)
        if project is None:
            return
        status = ProjectStatus.from_value(project.get("status") if isinstance(project, dict) else getattr(project, "status", None))
        is_pinned = bool(project.get("is_pinned", False) if isinstance(project, dict) else getattr(project, "is_pinned", False))

        menu = QMenu(self)
        menu.addAction(
            qta_icon("fa5s.thumbtack"),
            "取消置顶" if is_pinned else "置顶固定",
            lambda: self._toggle_pin_project(uuid),
        )
        menu.addAction(qta_icon("fa5s.folder-open"), "打开文件位置",
                       lambda: self._open_file_location(uuid))
        menu.addSeparator()
        menu.addAction(qta_icon("fa5s.edit"), "编辑项目",
                       lambda: self._edit_project(uuid))\
            .setEnabled(status.is_editable)
        menu.addAction(qta_icon("fa5s.undo"), "回滚项目",
                       lambda: self._open_rollback_dialog(uuid))\
            .setEnabled(status.is_editable)
        menu.addSeparator()
        menu.addAction(qta_icon("fa5s.trash-alt"), "删除项目",
                       lambda: self._delete_project(uuid, project))\
            .setEnabled(status.is_editable)
        menu.exec(self.list_widget.mapToGlobal(pos))

    # ── 动作（P2 占位 + 已实现项）───────────────────────────────────────────

    def _toggle_pin_project(self, uuid=None) -> None:
        if uuid is None:
            uuid = self.selected_uuid
        if not uuid:
            return
        try:
            toggle_pin(uuid)
        except Exception as e:
            logger.warning("[sidebar] 置顶失败: %s", e)
        self.refresh()

    def _open_file_location(self, uuid) -> None:
        file_path = os.path.normpath(str(project_file_path(uuid)))
        if not os.path.isfile(file_path):
            QMessageBox.warning(self, "错误", f"项目文件不存在：\n{file_path}")
            return
        try:
            if sys.platform.startswith("win"):
                subprocess.Popen(["explorer", f"/select,{file_path}"])
            elif sys.platform == "darwin":
                subprocess.Popen(["open", "-R", file_path])
            else:
                subprocess.Popen(["xdg-open", os.path.dirname(file_path)])
        except Exception as e:
            logger.warning("[sidebar] 打开位置失败: %s", e)

    def _new_project(self) -> None:
        from .dialogs import NewProjectDialog
        NewProjectDialog(self, self.refresh).exec()

    def _edit_project(self, uuid) -> None:
        from ...project_manager import get_project
        from .dialogs import NewProjectDialog
        project = get_project(uuid)
        if project is None:
            return
        pd = project.to_dict() if hasattr(project, "to_dict") else dict(project)
        NewProjectDialog(self, self._on_edit_done, mode="edit", project_data=pd).exec()

    def _on_edit_done(self) -> None:
        self.refresh()
        if self.selected_uuid:
            self.on_select(self.selected_uuid)

    def _open_rollback_dialog(self, uuid) -> None:
        from .dialogs.rollback import RollbackDialog
        dlg = RollbackDialog(self, uuid, on_rollback=self._on_rollback_done)
        dlg.exec()

    def _on_rollback_done(self, uuid) -> None:
        self.refresh()
        if self.on_select is not None:
            self.on_select(uuid)

    def _delete_project(self, uuid, project) -> None:
        from .dialogs.confirm import confirm_dialog
        from ...project_manager import delete_project
        if hasattr(project, "name"):
            name = getattr(project, "name", "")
        elif isinstance(project, dict):
            name = project.get("name", "")
        elif isinstance(project, str):
            name = project
        elif hasattr(project, "get"):
            name = project.get("name", "")
        else:
            name = ""
        name = str(name).strip() or "未命名项目"
        if not confirm_dialog(
            self,
            "确认删除",
            f"确定要删除项目「{name}」吗？\n\n此操作不可恢复，项目的所有数据将被永久删除。",
            default_yes=False,
        ):
            return
        if delete_project(uuid):
            is_current = (self.selected_uuid == uuid)
            self.refresh()
            if is_current:
                if self._item_widgets:
                    next_uuid = next(iter(self._item_widgets))
                    self.select_project(next_uuid, notify=True)
                else:
                    self.selected_uuid = None
                    if self.on_select is not None:
                        self.on_select(None)

    def _import_project(self) -> None:
        from PySide6.QtWidgets import QFileDialog
        from ...project_manager import import_project
        path, _ = QFileDialog.getOpenFileName(
            self, "导入项目", "", "JSON文件 (*.json);;所有文件 (*.*)"
        )
        if not path:
            return
        try:
            project = import_project(path)
        except Exception as e:
            QMessageBox.critical(self, "错误", f"导入失败：{e}")
            return
        if project:
            new_uuid = project.get("project_uuid")
            if new_uuid:
                self.selected_uuid = new_uuid
                if self.on_select is not None:
                    self.on_select(new_uuid)
            self.refresh()
            QMessageBox.information(
                self, "成功", f"项目已导入：{project.get('name', '')}"
            )

    def _export_project(self) -> None:
        if not self.selected_uuid:
            QMessageBox.information(self, "提示", "请先选择一个项目")
            return
        from .dialogs.import_export import export_project_dialog
        export_project_dialog(self, self.selected_uuid, on_done=lambda: None)

    def _open_settings(self) -> None:
        from .dialogs.settings import SettingsDialog
        from ...voice import get_voice
        get_voice().stop()
        SettingsDialog(self, on_close=self._on_settings_closed).exec()

    def _apply_fonts(self) -> None:
        """字体变更后重放（font_manager.refresh 回调链）。"""
        for row in self._item_widgets.values():
            row._apply_style()
        if self._new_btn:
            self._new_btn.setFont(font_manager.get("button"))
        for _b in getattr(self, "_io_buttons", ()):
            _b.setFont(font_manager.get("button"))
        self.search_edit.setFont(font_manager.get("body"))
        self.list_widget.setFont(font_manager.get("body"))
        if self._settings_btn:
            self._settings_btn.setFont(font_manager.get("button"))
