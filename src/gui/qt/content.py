"""Qt 内容区（替代 Tk ContentArea）。

P2：项目头部（名称 + 状态徽章）、双页签、欢迎页、异步保存桥。
P3：账单/工种 QTableView 列表（列宽权重、显隐预设、排序、拖拽、
    右键菜单、审核底色、孤儿红字）+ 指标卡 + 复制/粘贴/删除/软删除。

列解析逻辑镜像 Tk content.py（resolve_bill_columns 等），P5 清理时合并。
分类主-从窗格（P4 前半）已接入；编辑对话框/导出图片仍为 P4 范围，留占位回调。
"""
import copy
import queue
import threading
from types import SimpleNamespace

from PySide6.QtCore import QObject, QSize, Qt, Signal, QTimer
from PySide6.QtGui import QFont, QFontMetrics
from PySide6.QtWidgets import (
    QButtonGroup, QFrame, QHBoxLayout, QInputDialog, QLabel, QMenu,
    QMessageBox, QPushButton, QSizePolicy, QSplitter, QStackedWidget,
    QVBoxLayout, QWidget,
)

from ...logger import logger
from ...project_manager import get_project, update_project
from ...project_status import ProjectStatus
from ...config_loader import load_app, save_app
from ...billing import read_billing
from ...bill_recompute import (
    prepare_bill_calculations, recompute_bill_total, summarize_bill_calculations,
)
from ...bill_review import apply_bulk_review, is_bill_reviewed, set_bill_reviewed
from ...paste_actions import paste_bill, paste_trade_item, unique_category_after_paste
from ...billing_resolver import resolve_label
from ..font_manager import font_manager
from ..theme import (
    ACCENT, ACCENT_HOVER, ACCENT_PRESSED, APP_BG, CARD_BG, CARD_BORDER, DANGER, SEGMENT_BG, SEPARATOR,
    SYSTEM_GREEN, TEXT_PRIMARY, TEXT_SECONDARY, TEXT_TERTIARY,
    font_px,
)
from ..clipboard import AppClipboard
from ..common.reorder import move_item, reorder_subset_by_ids
from .save_bridge import ProjectSaveBridge
from .view_common import (
    CARD_QSS, SEGMENT_QSS, _amount_px, _build_metric_row,
    _make_metric_card, _metric_card_height,
)
from .category_utils import (
    _category_maps, _category_name, _category_id,
    _project_category_names, _safe_positive_float,
    _trade_item_category_name, resolve_bill_columns,
    resolve_worker_column_weights,
)
from .bill_view import BillViewMixin
from .worker_view import WorkerViewMixin
from .icons import (
    icon as ui_icon, ICON_BILL, ICON_CHECK, ICON_LIST, ICON_PLUS, ICON_PRICE,
    ICON_WARNING, ICON_WORKER,
)
from .status_badge import QtStatusBadge
from .bill_table import QtBillTable
from .worker_table import QtWorkerTable
from .category_list import QtCategoryList
from .action_bar import ActionBar

# ── 统一卡片 / 分段容器 QSS（与 theme.build_qss 全局体系一致的补充规则）─────────


# 指标卡片规格：(key, icon, icon_color, title, value_font_role, value_color, object_name)
# 图标统一中性灰，只有「总金额」用强调色——三张卡各一种颜色是最扎眼的杂色来源。
# 语义（如未设单价）由数值文字表达，不给图标上色。
_BILL_METRIC_SPECS = (
    ("amount", ICON_BILL, ACCENT, "总金额", "amount", ACCENT, "amount_value"),
    ("count", ICON_LIST, TEXT_SECONDARY, "明细记录", "subheading", None, ""),
    ("errors", ICON_CHECK, TEXT_SECONDARY, "数据校验", "subheading", None, ""),
)
_WORKER_METRIC_SPECS = (
    ("kinds", ICON_WORKER, ACCENT, "工作类型", "subheading", None, ""),
    ("priced", ICON_PRICE, TEXT_SECONDARY, "按单价计费", "subheading", None, ""),
    ("unpriced", ICON_WARNING, TEXT_SECONDARY, "未设单价", "subheading", None, ""),
)


# ── 分类辅助函数（镜像 Tk content.py，避免引入 Tk 模块）───────────────────────


# ── 列配置（镜像 Tk content.py，避免引入 Tk 模块）───────────────────────────

BILLS_MIN_WIDTH = 40

WORKER_MIN_WIDTH = 60

BILL_PRESET_QUICK_VIEW = ("审核", "工作内容", "公式", "单价", "金额")


class QtContentArea(BillViewMixin, WorkerViewMixin, QWidget):
    name_changed = Signal(str, str)    # (uuid, new_name)
    status_changed = Signal(str, str)  # (uuid, status_value)
    toast = Signal(str)

    def __init__(self, on_name_change=None, on_status_change=None,
                 on_new_project=None):
        super().__init__()
        self.current_uuid = None
        self.project_data = None
        self._tab = "bills"
        self._on_name_change = on_name_change
        self._on_status_change = on_status_change
        self._on_new_project = on_new_project if callable(on_new_project) else None
        self._editability = None
        self._app_config = load_app()
        self._op_map = self._app_config.get("symbol_mapping", {})
        self._clipboard = AppClipboard()

        # 兼容 shortcut_manager._execute_action 的属性访问
        self.tab_var = SimpleNamespace(get=lambda: self._tab)

        # 排序方向状态（与 Tk 一致：首次点击升序）
        self._bill_sort_descending = False
        self._worker_price_sort_descending = False
        self._worker_billing_sort_descending = False

        self._selected_category: str | None = None
        self._category_ratio_pending = True

        self._bill_weights: dict[str, float] = {}
        self._worker_weights: dict[str, float] = {}

        self._save_bridge = ProjectSaveBridge(self)
        self._save_bridge.save_error.connect(self._on_save_error)
        self.toast.connect(self._show_toast)

        self._build_ui()
        self._show_welcome()
        self._tip_bar.show_once()

    # ── 只读 / 编辑能力 ────────────────────────────────────────────────────

    @property
    def _editable(self) -> bool:
        if self._editability is None:
            return True
        return self._editability.is_editable

    # ── UI 构建 ─────────────────────────────────────────────────────────────

    def _build_ui(self) -> None:
        # 背景用 objectName 限定，避免局部 QSS 级联覆盖子控件
        # （否则「记一笔」等主按钮会被刷成与内容区同色，全局按钮配色失效）。
        self.setObjectName("content")
        self.setStyleSheet(f"QWidget#content {{ background: {APP_BG}; }}")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 12, 24, 12)
        layout.setSpacing(6)

        # 头部：项目名（22px 大标题）+ 状态 pill + 唯一主按钮「记一笔」
        header = QHBoxLayout()
        header.setSpacing(10)
        self._header_name_lbl = QLabel("")
        self._header_name_lbl.setObjectName("page_title")
        self._header_name_lbl.setFont(font_manager.get("title"))
        self._header_name_lbl.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        self._header_name_lbl.setTextInteractionFlags(Qt.TextSelectableByMouse)
        header.addWidget(self._header_name_lbl, 1)
        self._toggle_badge = QtStatusBadge()
        self._toggle_badge.mousePressEvent = lambda e: self._toggle_status()
        header.addWidget(self._toggle_badge)
        self._bill_add_btn = QPushButton("记一笔新账")
        self._bill_add_btn.setIcon(ui_icon(ICON_PLUS, "#ffffff"))
        self._bill_add_btn.setIconSize(QSize(18, 18))
        self._bill_add_btn.clicked.connect(self._add_bill)
        self._bill_add_btn.setStyleSheet(
            f"QPushButton {{ background: {ACCENT}; color: #ffffff; border: none; border-radius: 8px;"
            f" padding: 8px 18px; font-weight: bold; font-size: {font_px('body_bold')}px; min-height: 38px; }}"
            f"QPushButton:hover {{ background: {ACCENT_HOVER}; }}"
            f"QPushButton:pressed {{ background: {ACCENT_PRESSED}; }}"
        )
        header.addWidget(self._bill_add_btn)
        layout.addLayout(header)

        # 头部与页签间的细分隔线
        header_sep = QFrame()
        header_sep.setStyleSheet(f"background: {SEPARATOR}; border: none;")
        header_sep.setFixedHeight(1)
        layout.addWidget(header_sep)

        # 页签：账单管理 / 工作类型（右侧提供直观的列显示模式选择）
        tabs = QHBoxLayout()
        tabs.setSpacing(4)
        tab_segment = QFrame()
        tab_segment.setStyleSheet(SEGMENT_QSS)
        self._tab_segment = tab_segment
        seg_layout = QHBoxLayout(tab_segment)
        seg_layout.setContentsMargins(0, 0, 0, 0)
        seg_layout.setSpacing(2)
        self._tab_group = QButtonGroup(self)
        self._tab_group.setExclusive(True)
        self._tab_buttons: dict[str, QPushButton] = {}
        for value, text, menu_fn in (
            ("bills", "账单管理", self._show_bill_mode_menu),
            ("workers", "工作类型设置", self._show_worker_mode_menu),
        ):
            btn = QPushButton(text)
            btn.setCheckable(True)
            btn.setProperty("tab", True)
            btn.clicked.connect(lambda _=False, v=value: self._switch_tab(v))
            btn.setContextMenuPolicy(Qt.CustomContextMenu)
            btn.customContextMenuRequested.connect(
                lambda _pos, fn=menu_fn: fn()
            )
            self._tab_group.addButton(btn)
            self._tab_buttons[value] = btn
            seg_layout.addWidget(btn)
        tabs.addWidget(tab_segment)
        tabs.addStretch(1)

        # 列显示模式选择段（长辈友好：无须用快捷键）
        mode_segment = QFrame()
        mode_segment.setStyleSheet(SEGMENT_QSS)
        self._mode_segment = mode_segment
        mode_layout = QHBoxLayout(mode_segment)
        mode_layout.setContentsMargins(0, 0, 0, 0)
        mode_layout.setSpacing(2)
        self._mode_group = QButtonGroup(self)
        self._mode_group.setExclusive(True)
        self._mode_buttons: dict[str, QPushButton] = {}
        for m_val, m_text in (
            ("simple", "极简速览 (推荐)"),
            ("audit", "查账模式"),
            ("complex", "显示全部"),
        ):
            m_btn = QPushButton(m_text)
            m_btn.setCheckable(True)
            m_btn.setProperty("tab", True)
            m_btn.setToolTip(f"切换至【{m_text}】表格显示列")
            m_btn.clicked.connect(lambda _=False, v=m_val: self._switch_bill_mode(v))
            self._mode_group.addButton(m_btn)
            self._mode_buttons[m_val] = m_btn
            mode_layout.addWidget(m_btn)
        tabs.addWidget(mode_segment)
        layout.addLayout(tabs)

        # 内容栈：welcome / bills / workers
        self._stack = QStackedWidget(self)
        self._welcome_page = QWidget()
        wl = QVBoxLayout(self._welcome_page)
        w_card = QFrame()
        w_card.setObjectName("welcome_card")
        w_card.setStyleSheet(
            f"QFrame#welcome_card {{ background: {CARD_BG}; border: 1px solid {CARD_BORDER}; border-radius: 12px; }}"
            f"QLabel {{ background: transparent; border: none; }}"
        )
        w_card.setFixedWidth(520)
        w_card.setMinimumHeight(300)
        w_card_layout = QVBoxLayout(w_card)
        w_card_layout.setContentsMargins(36, 28, 36, 28)
        w_card_layout.setSpacing(16)
        w_icon = QLabel()
        w_icon.setPixmap(ui_icon(ICON_BILL, TEXT_TERTIARY).pixmap(48, 48))
        w_icon.setAlignment(Qt.AlignCenter)
        w_card_layout.addWidget(w_icon)
        w_title = QLabel("欢迎使用")
        w_title.setObjectName("welcome_title")
        w_title.setAlignment(Qt.AlignCenter)
        w_title.setFont(font_manager.get("heading"))
        w_card_layout.addWidget(w_title)
        w_hint = QLabel("点击左侧【新建项目】开始记账\n或选择一个已有项目查看")
        w_hint.setAlignment(Qt.AlignCenter)
        w_hint.setWordWrap(True)
        w_hint.setStyleSheet(f"color: {TEXT_SECONDARY}; background: transparent; border: none;")
        w_card_layout.addWidget(w_hint)
        w_new_btn = QPushButton("新建项目")
        w_new_btn.setIcon(ui_icon(ICON_PLUS))
        w_new_btn.setIconSize(QSize(16, 16))
        w_new_btn.setMinimumWidth(150)
        if self._on_new_project is not None:
            w_new_btn.clicked.connect(self._on_new_project)
        w_new_btn.setEnabled(self._on_new_project is not None)
        w_card_layout.addWidget(w_new_btn, 0, Qt.AlignCenter)
        w_row = QHBoxLayout()
        w_row.addStretch(1)
        w_row.addWidget(w_card, 0, Qt.AlignVCenter)
        w_row.addStretch(1)
        wl.addLayout(w_row)
        wl.setContentsMargins(0, 24, 0, 24)
        self._stack.addWidget(self._welcome_page)

        # ── 账单页 ──
        self._bills_page = QWidget()
        bl = QVBoxLayout(self._bills_page)
        bl.setContentsMargins(0, 0, 0, 0)
        bl.setSpacing(8)

        # 指标区：横向充满的 3 列看板卡片网格（与工作类型页共用工厂函数）
        metrics, self._metric_labels = _build_metric_row(_BILL_METRIC_SPECS)
        bl.addLayout(metrics)

        # 空状态提示（无账单时显示）
        self._bills_empty_hint = QFrame()
        self._bills_empty_hint.setStyleSheet(
            f"background: {SEGMENT_BG}; border: none; border-radius: 8px;"
        )
        empty_layout = QHBoxLayout(self._bills_empty_hint)
        empty_layout.setContentsMargins(16, 10, 16, 10)
        empty_lbl = QLabel("还没有账单。先到【工作类型】添加工作项目，再点「记一笔」开始记账。")
        empty_lbl.setStyleSheet(f"color: {TEXT_SECONDARY};")
        empty_layout.addWidget(empty_lbl)
        empty_layout.addStretch(1)
        self._bills_empty_hint.setVisible(False)
        bl.addWidget(self._bills_empty_hint)

        # 选中行操作条（置于表格顶部工具栏位置，紧贴表格头，消除底部断层）
        self._action_bar = ActionBar(self._bills_page)
        self._action_bar.edit_requested.connect(self._edit_bill)
        self._action_bar.up_requested.connect(lambda row: self._move_bill(row, -1))
        self._action_bar.down_requested.connect(lambda row: self._move_bill(row, 1))
        self._action_bar.copy_requested.connect(self._copy_bills)
        self._action_bar.paste_requested.connect(self._paste_bills)
        self._action_bar.delete_requested.connect(self._delete_bill)
        bl.addWidget(self._action_bar)

        self._bills_table = QtBillTable(self._op_map, self._bills_page)
        self._bills_table.edit_requested.connect(self._edit_bill)
        self._bills_table.sort_requested.connect(self._sort_bills)
        self._bills_table.column_resized.connect(self._on_bill_column_resize)
        self._bills_table.rows_moved.connect(self._on_bills_rows_moved)
        self._bills_table.copy_requested.connect(self._copy_bills)
        self._bills_table.paste_requested.connect(self._paste_bills)
        self._bills_table.action_triggered.connect(self._on_bill_action)
        self._bills_table.review_toggle_requested.connect(self._toggle_bill_review)
        bl.addWidget(self._bills_table, 1)

        self._bills_table.selectionModel().selectionChanged.connect(
            self._on_bill_selection_changed
        )
        self._stack.addWidget(self._bills_page)

        # ── 工作类型页：分类主-从窗格（左侧分类列表 + 右侧工种表）──
        self._workers_page = QWidget()
        wl2 = QVBoxLayout(self._workers_page)
        wl2.setContentsMargins(0, 0, 0, 0)
        wl2.setSpacing(8)

        # 顶部骨架与账单页严格同构：指标行 + 操作条，切换页签时高度一致不跳变。
        w_metrics, self._worker_metric_labels = _build_metric_row(_WORKER_METRIC_SPECS)
        wl2.addLayout(w_metrics)

        self._worker_action_bar = ActionBar(self._workers_page)
        self._worker_action_bar.edit_requested.connect(self._edit_trade_item_at)
        self._worker_action_bar.up_requested.connect(
            lambda row: self._on_worker_action(row, "up")
        )
        self._worker_action_bar.down_requested.connect(
            lambda row: self._on_worker_action(row, "down")
        )
        self._worker_action_bar.copy_requested.connect(self._copy_workers)
        self._worker_action_bar.paste_requested.connect(self._paste_workers)
        self._worker_action_bar.delete_requested.connect(
            lambda row: self._on_worker_action(row, "delete")
        )
        wl2.addWidget(self._worker_action_bar)

        self._category_splitter = QSplitter(Qt.Horizontal, self._workers_page)
        self._category_splitter.setHandleWidth(5)
        self._category_splitter.setChildrenCollapsible(False)

        self._category_list = QtCategoryList(self._category_splitter)
        self._category_list.setMinimumWidth(120)
        self._category_list.category_selected.connect(self._on_category_selected)
        self._category_list.menu_action.connect(self._on_category_menu_action)
        self._category_splitter.addWidget(self._category_list)

        workers_right = QWidget(self._category_splitter)
        workers_right.setMinimumWidth(280)
        wr_layout = QVBoxLayout(workers_right)
        wr_layout.setContentsMargins(0, 0, 0, 0)
        wr_layout.setSpacing(0)
        self._workers_table = QtWorkerTable(workers_right)
        self._workers_table.edit_requested.connect(self._edit_trade_item_at)
        self._workers_table.sort_requested.connect(self._sort_workers)
        self._workers_table.column_resized.connect(self._on_worker_column_resize)
        self._workers_table.rows_moved.connect(self._on_workers_rows_moved)
        self._workers_table.copy_requested.connect(self._copy_workers)
        self._workers_table.paste_requested.connect(self._paste_workers)
        self._workers_table.action_triggered.connect(self._on_worker_action)
        self._workers_table.selectionModel().selectionChanged.connect(
            self._on_worker_selection_changed
        )
        wr_layout.addWidget(self._workers_table, 1)
        self._workers_empty_hint = QFrame(workers_right)
        self._workers_empty_hint.setStyleSheet(
            f"background: {SEGMENT_BG}; border: none; border-radius: 8px;"
        )
        hint_layout = QVBoxLayout(self._workers_empty_hint)
        hint_layout.setContentsMargins(16, 16, 16, 16)
        hint_lbl = QLabel("还没有工作类型。\n在左侧列表空白处点右键，或点击【工作类型】页签选「添加分类」，\n然后添加工种和单价，例如：瓦工 300元/天。")
        hint_lbl.setStyleSheet(f"color: {TEXT_SECONDARY};")
        hint_lbl.setWordWrap(True)
        hint_layout.addWidget(hint_lbl)
        hint_layout.addStretch(1)
        self._workers_empty_hint.setVisible(False)
        wr_layout.addWidget(self._workers_empty_hint, 1)
        self._category_splitter.addWidget(workers_right)

        self._category_ratio_timer = QTimer(self)
        self._category_ratio_timer.setSingleShot(True)
        self._category_ratio_timer.setInterval(300)
        self._category_ratio_timer.timeout.connect(self._on_category_ratio_timeout)
        self._category_splitter.splitterMoved.connect(self._on_category_splitter_moved)

        wl2.addWidget(self._category_splitter, 1)
        self._stack.addWidget(self._workers_page)

        layout.addWidget(self._stack, 1)

        # 底部提示条（可关闭，关闭后不再显示）
        from .onboarding import TipBar
        self._tip_bar = TipBar(self)
        layout.addWidget(self._tip_bar)

    # ── 状态切换 ────────────────────────────────────────────────────────────

    def _toggle_status(self) -> None:
        if not self.project_data:
            return
        now = ProjectStatus.from_value(self.project_data.get("status"))
        new_status = (ProjectStatus.DONE if now == ProjectStatus.EDITING
                      else ProjectStatus.EDITING)
        self.project_data["status"] = new_status.value
        self._save_bridge.schedule(self.current_uuid, self.project_data)
        self._toggle_badge.set_status(new_status)
        if self._on_status_change is not None:
            try:
                self._on_status_change(self.current_uuid, new_status.value)
            except Exception as ex:
                logger.warning("通知侧边栏项目状态更新失败: %s", ex)
        if self._editability is not None:
            self._editability.refresh()
        self._apply_editability()

    def _switch_tab(self, tab: str) -> None:
        self._tab = tab
        for value, btn in self._tab_buttons.items():
            btn.setChecked(value == tab)
        if tab == "bills":
            self._stack.setCurrentWidget(self._bills_page)
        else:
            self._stack.setCurrentWidget(self._workers_page)
            QTimer.singleShot(0, self._apply_category_ratio)

    def _apply_editability(self) -> None:
        editable = self._editable
        self._bills_table.set_editable(editable)
        self._workers_table.set_editable(editable)
        self._bill_add_btn.setEnabled(editable)
        self._category_list.set_editable(editable)
        self._sync_action_bar()
        self._sync_worker_action_bar()

    def _on_bill_selection_changed(self, *_args) -> None:
        self._sync_action_bar()

    def _on_worker_selection_changed(self, *_args) -> None:
        self._sync_worker_action_bar()

    def _selected_bill_rows(self) -> list[int]:
        sel = self._bills_table.selectionModel()
        if sel is None:
            return []
        return sorted({i.row() for i in sel.selectedRows()})

    def _selected_worker_rows(self) -> list[int]:
        sel = self._workers_table.selectionModel()
        if sel is None:
            return []
        return sorted({i.row() for i in sel.selectedRows()})

    def _sync_action_bar(self) -> None:
        if getattr(self, "_action_bar", None) is None:
            return
        try:
            self._action_bar.set_rows(self._selected_bill_rows(), self._editable)
        except RuntimeError:
            pass

    def _sync_worker_action_bar(self) -> None:
        if getattr(self, "_worker_action_bar", None) is None:
            return
        try:
            self._worker_action_bar.set_rows(
                self._selected_worker_rows(), self._editable
            )
        except RuntimeError:
            pass

    # ── 欢迎 / 加载 / 清理 ─────────────────────────────────────────────────

    def _show_welcome(self) -> None:
        self.current_uuid = None
        self.project_data = None
        self._selected_category = None
        self._header_name_lbl.setText("欢迎使用")
        self._toggle_badge.set_status(None)
        self._toggle_badge.hide()
        self._bill_add_btn.hide()
        self._tab_segment.hide()
        self._stack.setCurrentWidget(self._welcome_page)
        self._tab_buttons["bills"].setChecked(False)
        self._tab_buttons["workers"].setChecked(False)

    def load_project(self, uuid: str) -> None:
        project = get_project(uuid)
        if project is None:
            logger.warning("[content] 项目不存在: %s", uuid)
            return
        self.current_uuid = uuid
        self.project_data = project
        self._app_config = load_app()
        self._op_map = self._app_config.get("symbol_mapping", {})
        self._category_ratio_pending = True
        self._toggle_badge.show()
        self._bill_add_btn.show()
        self._tab_segment.show()
        self._render()
        self._apply_editability()

    def _render(self) -> None:
        p = self.project_data
        name = p.get("name", "")
        self._header_name_lbl.setText(name)
        self._toggle_badge.set_status(ProjectStatus.from_value(p.get("status")))
        self._render_bills()
        self._render_workers()
        self._switch_tab(self._tab)

    def clear(self) -> None:
        self._show_welcome()


    # ── 账单页渲染 ─────────────────────────────────────────────────────────


    # ── 账单操作 ───────────────────────────────────────────────────────────


    # ── 复制 / 粘贴：账单 ──


    # ── 工作类型操作 ────────────────────────────────────────────────────────


    # ── 复制 / 粘贴：工作类型 ──


    # ── 列显隐预设（右键账单页签）──────────────────────────────────────────


    # ── P4 业务对话框接线 ─────────────────────────────────────────────────


    def _export_image(self) -> None:
        if not self.project_data:
            return
        from .dialogs.export_image import ExportImageDialog
        dlg = ExportImageDialog(self, self.project_data, on_done=lambda: None)
        dlg.exec()

    # ── 分类管理（主-从窗格：右键菜单 / 页签菜单入口）──────────────────────


    # ── 分类列宽比例持久化 ──────────────────────────────────────────────────


    def _restore_defaults(self) -> None:
        """恢复默认工作类型：以 app_config 默认数据重置 trade_items/category_order。"""
        if not self._editable or not self.project_data:
            return
        if not self._confirm_delete("确认", "恢复默认工作类型？当前所有工作类型将被替换。"):
            return
        from ...project_manager import _load_default_items, _load_default_categories
        self.project_data["trade_items"] = _load_default_items()
        self.project_data["category_order"] = [
            c.to_dict() if hasattr(c, "to_dict") else dict(c)
            for c in _load_default_categories()
        ]
        self._selected_category = None
        self._save_bridge.schedule(self.current_uuid, self.project_data)
        self._render_workers()
        self._render_bills()
        self.toast.emit("已恢复默认工作类型")


    # ── 通用 ───────────────────────────────────────────────────────────────

    def _confirm_delete(self, title: str, message: str) -> bool:
        return self._confirm(title, message, default_yes=False)

    def _confirm_replace(self, title: str, message: str) -> bool:
        return self._confirm(title, message, default_yes=True)

    def _confirm(self, title: str, message: str, default_yes: bool) -> bool:
        from .dialogs.confirm import confirm_dialog
        return confirm_dialog(self, title, message, default_yes=default_yes)

    def _error_box(self, title: str, message: str) -> None:
        QMessageBox.critical(self, title, message)

    # ── 外部接口 ────────────────────────────────────────────────────────────

    def set_editability(self, policy) -> None:
        self._editability = policy
        self._apply_editability()

    def get_project_status(self):
        if not self.project_data:
            return None
        return ProjectStatus.from_value(self.project_data.get("status"))

    def refresh_app_settings(self) -> None:
        self._app_config = load_app()
        self._op_map = self._app_config.get("symbol_mapping", {})
        if self.current_uuid and self.project_data:
            self._render()

    def flush_project_save(self, timeout: float = 2.0) -> bool:
        return self._save_bridge.flush(timeout)

    def shutdown(self) -> None:
        """停止后台任务（窗口关闭时由 MainWindow 调用，须先于对象销毁）。"""
        self._save_bridge.close()

    def _show_toast(self, text: str, level: str = "success") -> None:
        from .feedback import show_toast
        show_toast(self, text, level)

    def _on_save_error(self, message: str) -> None:
        logger.error("项目保存失败需要用户处理: %s", message)
        self._show_toast(f"项目保存失败，数据未写入磁盘：{message}", "error")

    def _apply_fonts(self) -> None:
        """字体变更后重放（font_manager.refresh 回调链）。"""
        self._header_name_lbl.setFont(font_manager.get("title"))
        for btn in self._tab_buttons.values():
            btn.setFont(font_manager.get("body"))
        self._category_list.refresh_fonts()
