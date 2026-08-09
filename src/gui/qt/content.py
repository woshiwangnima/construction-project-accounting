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

from qtawesome import icon as qta_icon
from PySide6.QtCore import QObject, QSize, Qt, Signal, QTimer
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
    SYSTEM_GREEN, TEXT_PRIMARY, TEXT_SECONDARY,
)
from ..clipboard import AppClipboard
from ..widgets.reorder import move_item, reorder_subset_by_ids
from .status_badge import QtStatusBadge
from .bill_table import QtBillTable
from .worker_table import QtWorkerTable
from .category_list import QtCategoryList
from .action_bar import ActionBar

# ── 统一卡片 / 分段容器 QSS（与 theme.build_qss 全局体系一致的补充规则）─────────
CARD_QSS = (
    f"background: {CARD_BG}; border: 1px solid {CARD_BORDER};"
    f"border-radius: 8px; padding: 10px 10px;"
)
SEGMENT_QSS = f"background: {SEGMENT_BG}; border-radius: 8px; padding: 2px;"

# ── 分类辅助函数（镜像 Tk content.py，避免引入 Tk 模块）───────────────────────


def _category_name(category) -> str:
    if hasattr(category, "name"):
        return category.name
    if isinstance(category, dict):
        return category.get("name", "")
    return str(category)


def _category_id(category) -> str:
    if hasattr(category, "id"):
        return category.id
    if isinstance(category, dict):
        return category.get("id", "")
    return ""


def _category_maps(project) -> tuple[dict[str, str], dict[str, str]]:
    id_to_name = {}
    name_to_id = {}
    for category in (project or {}).get("category_order", []) or []:
        cid = _category_id(category)
        name = _category_name(category)
        if cid:
            id_to_name[cid] = name
        if name:
            name_to_id[name] = cid
    return id_to_name, name_to_id


def _trade_item_category_name(item, project, category_maps=None) -> str:
    if item.get("category"):
        return item.get("category", "")
    id_to_name, _ = category_maps or _category_maps(project)
    return id_to_name.get(item.get("category_id", ""), item.get("category_id", ""))


def _project_category_names(project) -> list[str]:
    category_maps = _category_maps(project)
    names = [_category_name(c) for c in (project or {}).get("category_order", []) or []]
    for item in (project or {}).get("trade_items", []) or []:
        name = _trade_item_category_name(item, project, category_maps)
        if name and name not in names:
            names.append(name)
    return names

# ── 列配置（镜像 Tk content.py，避免引入 Tk 模块）───────────────────────────

BILLS_MIN_WIDTH = 40

WORKER_COLUMNS = ("名称", "单价", "单位", "计费类型", "操作")
WORKER_MIN_WIDTH = 60
WORKER_DEFAULT_WEIGHTS = {
    "名称": 0.3571428571,    # 5/14
    "单价": 0.2142857143,    # 3/14
    "单位": 0.2142857143,
    "计费类型": 0.2142857143,
    "操作": 0.06,
}

BILL_PRESET_QUICK_VIEW = ("审核", "工作内容", "公式", "单价", "金额")
BILL_ACTION_COL = "操作"


def _safe_positive_float(v) -> float | None:
    try:
        x = float(v)
        if x > 0:
            return x
    except (TypeError, ValueError):
        pass
    return None


def resolve_bill_columns(
    project_data: dict,
    app_config: dict | None = None,
) -> tuple[list[str], dict[str, float], list[str]]:
    """返回 (列顺序, 当前模式权重[全部11列], 隐藏列列表)。与 Tk 版一致。"""
    app_config = app_config if app_config is not None else load_app()
    defaults = app_config.get("default_bill_column_widths_data", [])
    columns = [d["name"] for d in defaults]

    saved = (project_data or {}).get("bill_column_widths", []) or []
    saved_map = {}
    for item in saved:
        if isinstance(item, dict) and "name" in item:
            w = _safe_positive_float(item.get("weight"))
            if w is not None:
                saved_map[item["name"]] = w

    base = {}
    for d in defaults:
        base[d["name"]] = saved_map.get(d["name"], d["weight"])

    mode = (project_data or {}).get("bill_display_mode", "simple")
    visible = (project_data or {}).get("bill_visible_columns") or []
    if visible:
        visible_set = set(visible)
        hidden = [c for c in columns if c not in visible_set]
        hidden = [c for c in hidden if c != BILL_ACTION_COL]
    elif mode == "simple":
        hidden = [d["name"] for d in defaults if not d.get("show_in_simple", True)]
    elif mode == "audit":
        hidden = [d["name"] for d in defaults if not d.get("show_in_audit", True)]
    else:
        hidden = []
    if not hidden:
        return columns, base, []

    visible = [c for c in columns if c not in hidden]
    total_hidden = sum(base[c] for c in hidden)
    total_visible = sum(base[c] for c in visible)

    if total_visible <= 0:
        return columns, base, hidden

    ratio = 1 + total_hidden / total_visible
    weights = {}
    for col in columns:
        weights[col] = base.get(col, 0) * ratio if col in visible else base.get(col, 0)

    return columns, weights, hidden


def resolve_worker_column_weights(project_data: dict, app_config: dict | None = None) -> dict:
    """解析 worker 表格列权重：项目保存值 → app_config 默认 → 硬编码。"""
    saved = (project_data or {}).get("worker_column_widths", {}) or {}
    try:
        app_config = app_config if app_config is not None else load_app()
        app_defaults = app_config.get("default_worker_column_widths", {}) or {}
    except Exception:
        app_defaults = {}

    result: dict[str, float] = {}
    for col in WORKER_COLUMNS:
        w = _safe_positive_float(saved.get(col))
        if w is not None:
            result[col] = w
            continue
        w = _safe_positive_float(app_defaults.get(col))
        if w is not None:
            result[col] = w
            continue
        result[col] = WORKER_DEFAULT_WEIGHTS[col]
    return result


class ProjectSaveBridge(QObject):
    """异步项目保存桥：快照合并 + 单 worker 串行写入 + 状态信号。"""

    save_error = Signal(str)
    save_state = Signal(str, str)  # (state, stamp)：saving/saved/failed

    def __init__(self, parent=None):
        super().__init__(parent)
        self._lock = threading.Lock()
        self._pending: tuple[str, dict] | None = None
        self._running = False
        self._idle = threading.Event()
        self._idle.set()

    def schedule(self, uuid: str, project_data) -> None:
        if not uuid or not project_data:
            return
        try:
            snapshot = copy.deepcopy(project_data)
        except Exception:
            snapshot = (project_data.to_dict()
                        if hasattr(project_data, "to_dict")
                        else dict(project_data))
        with self._lock:
            self._pending = (uuid, snapshot)
            self._idle.clear()
            if self._running:
                return
            self._running = True
            self.save_state.emit("saving", "")
        threading.Thread(target=self._drain, name="project-save", daemon=True).start()

    def _drain(self) -> None:
        while True:
            with self._lock:
                pending = self._pending
                self._pending = None
                if pending is None:
                    self._running = False
                    self._idle.set()
                    return
            uuid, snapshot = pending
            try:
                update_project(uuid, snapshot)
                from .feedback import now_stamp
                self.save_state.emit("saved", now_stamp())
            except Exception as exc:  # pragma: no cover - defensive worker boundary
                logger.warning("项目后台保存失败 uuid=%s: %s", uuid[:16], exc, exc_info=True)
                self.save_error.emit(str(exc))
                self.save_state.emit("failed", "")

    def flush(self, timeout: float = 2.0) -> bool:
        return self._idle.wait(max(float(timeout), 0.0))


class QtContentArea(QWidget):
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
        self.setStyleSheet("QWidget#content { background: #f7f8fa; }")
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
        self._bill_add_btn = QPushButton(" + 记一笔新账 ")
        self._bill_add_btn.setIcon(qta_icon("fa5s.plus-circle"))
        self._bill_add_btn.setIconSize(QSize(18, 18))
        self._bill_add_btn.clicked.connect(self._add_bill)
        self._bill_add_btn.setStyleSheet(
            f"QPushButton {{ background: {ACCENT}; color: #ffffff; border: none; border-radius: 8px;"
            f" padding: 8px 18px; font-weight: bold; font-size: 15px; min-height: 38px; }}"
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
            ("bills", " 📋 账单管理 ", self._show_bill_mode_menu),
            ("workers", " 👷 工作类型设置 ", self._show_worker_mode_menu),
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
            ("simple", "⚡ 极简速览 (推荐)"),
            ("audit", "📋 查账模式"),
            ("complex", "🔍 显示全部"),
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
        w_icon.setPixmap(qta_icon("fa5s.hand-sparkles").pixmap(48, 48))
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
        w_new_btn.setIcon(qta_icon("fa5s.plus"))
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

        # 指标区：横向充满的 3 列看板卡片网格
        metrics = QHBoxLayout()
        metrics.setSpacing(12)
        self._metric_labels: dict[str, QLabel] = {}

        # 1. 总金额卡片 (含图标)
        amount_card = QFrame()
        amount_card.setProperty("card", True)
        amount_card.setStyleSheet(CARD_QSS)
        amount_outer = QHBoxLayout(amount_card)
        amount_outer.setContentsMargins(14, 10, 14, 10)
        amount_outer.setSpacing(12)
        amount_icon = QLabel()
        amount_icon.setStyleSheet("border: none; background: transparent;")
        amount_icon.setPixmap(qta_icon("fa5s.wallet", color=ACCENT).pixmap(24, 24))
        amount_outer.addWidget(amount_icon)
        amount_layout = QVBoxLayout()
        amount_layout.setSpacing(2)
        amount_title = QLabel("总金额")
        amount_title.setStyleSheet(f"color: {TEXT_SECONDARY}; font-size: 13px; font-weight: bold; border: none;")
        amount_value = QLabel("")
        amount_value.setObjectName("amount_value")
        amount_value.setFont(font_manager.get("amount"))
        amount_value.setStyleSheet(f"color: {ACCENT}; font-weight: bold; border: none;")
        amount_layout.addWidget(amount_title)
        amount_layout.addWidget(amount_value)
        amount_outer.addLayout(amount_layout, 1)
        self._metric_labels["amount"] = amount_value
        metrics.addWidget(amount_card, 1)

        # 2. 明细记录卡片 (含图标)
        count_card = QFrame()
        count_card.setProperty("card", True)
        count_card.setStyleSheet(CARD_QSS)
        count_outer = QHBoxLayout(count_card)
        count_outer.setContentsMargins(14, 10, 14, 10)
        count_outer.setSpacing(12)
        count_icon = QLabel()
        count_icon.setStyleSheet("border: none; background: transparent;")
        count_icon.setPixmap(qta_icon("fa5s.list-alt", color=TEXT_SECONDARY).pixmap(24, 24))
        count_outer.addWidget(count_icon)
        count_layout = QVBoxLayout()
        count_layout.setSpacing(2)
        count_title = QLabel("明细记录")
        count_title.setStyleSheet(f"color: {TEXT_SECONDARY}; font-size: 13px; font-weight: bold; border: none;")
        count_value = QLabel("")
        count_value.setFont(font_manager.get("subheading"))
        count_value.setStyleSheet(f"color: {TEXT_PRIMARY}; font-weight: bold; border: none;")
        count_layout.addWidget(count_title)
        count_layout.addWidget(count_value)
        count_outer.addLayout(count_layout, 1)
        self._metric_labels["count"] = count_value
        metrics.addWidget(count_card, 1)

        # 3. 数据校验卡片 (含图标)
        status_card = QFrame()
        status_card.setProperty("card", True)
        status_card.setStyleSheet(CARD_QSS)
        status_outer = QHBoxLayout(status_card)
        status_outer.setContentsMargins(14, 10, 14, 10)
        status_outer.setSpacing(12)
        status_icon = QLabel()
        status_icon.setStyleSheet("border: none; background: transparent;")
        status_icon.setPixmap(qta_icon("fa5s.shield-alt", color=SYSTEM_GREEN).pixmap(24, 24))
        status_outer.addWidget(status_icon)
        status_layout = QVBoxLayout()
        status_layout.setSpacing(2)
        status_title = QLabel("数据校验")
        status_title.setStyleSheet(f"color: {TEXT_SECONDARY}; font-size: 13px; font-weight: bold; border: none;")
        errors_value = QLabel("")
        errors_value.setFont(font_manager.get("subheading"))
        status_layout.addWidget(status_title)
        status_layout.addWidget(errors_value)
        status_outer.addLayout(status_layout, 1)
        self._metric_labels["errors"] = errors_value
        metrics.addWidget(status_card, 1)

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

    def _on_bill_selection_changed(self, *_args) -> None:
        self._sync_action_bar()

    def _selected_bill_rows(self) -> list[int]:
        sel = self._bills_table.selectionModel()
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

    def _switch_bill_mode(self, mode: str) -> None:
        if not self.project_data or not self.current_uuid:
            return
        self.project_data["bill_display_mode"] = mode
        if "bill_visible_columns" in self.project_data:
            del self.project_data["bill_visible_columns"]
        self._save_bridge.schedule(self.current_uuid, self.project_data)
        self._render_bills()

    # ── 账单页渲染 ─────────────────────────────────────────────────────────

    def _render_bills(self) -> None:
        if not self.project_data:
            return
        p = self.project_data
        bills = p.get("bills", []) or []
        trade_items = p.get("trade_items", []) or []
        calculations, total, err_cnt = summarize_bill_calculations(
            bills, trade_items, self._op_map
        )
        columns, weights, hidden = resolve_bill_columns(p, self._app_config)
        self._bill_weights = weights

        cur_mode = p.get("bill_display_mode", "simple")
        if hasattr(self, "_mode_buttons") and cur_mode in self._mode_buttons:
            self._mode_buttons[cur_mode].setChecked(True)

        self._bills_table.set_columns(columns, hidden)
        self._bills_table.set_column_weights(weights, hidden)
        self._bills_table.update_data(bills, trade_items, self._op_map, calculations)

        self._metric_labels["amount"].setText(f"￥{total:.2f}")
        self._metric_labels["count"].setText(str(len(bills)))
        if err_cnt:
            self._metric_labels["errors"].setText(f"⚠️ {err_cnt} 处错误")
            self._metric_labels["errors"].setStyleSheet(f"color: {DANGER}; font-weight: bold;")
        else:
            self._metric_labels["errors"].setText("✓ 无错误")
            self._metric_labels["errors"].setStyleSheet(f"color: {SYSTEM_GREEN}; font-weight: bold;")
        self._bills_empty_hint.setVisible(len(bills) == 0)
        self._sync_action_bar()

    def _render_workers(self) -> None:
        if not self.project_data:
            return
        p = self.project_data
        items = p.get("trade_items", []) or []
        cats = _project_category_names(p)
        category_maps = _category_maps(p)
        counts: dict[str, int] = {}
        for ti in items:
            cat = _trade_item_category_name(ti, p, category_maps)
            if cat:
                counts[cat] = counts.get(cat, 0) + 1
        ordered_counts = {cat: counts.get(cat, 0) for cat in cats}

        if self._selected_category not in cats:
            self._selected_category = cats[0] if cats else None
        self._category_list.set_categories(ordered_counts)
        self._category_list.set_selected(self._selected_category)
        has_cats = bool(cats)
        self._workers_table.setVisible(has_cats)
        self._workers_empty_hint.setVisible(not has_cats)

        weights = resolve_worker_column_weights(p, self._app_config)
        self._worker_weights = weights
        self._workers_table.set_columns(list(WORKER_COLUMNS), [])
        self._workers_table.set_column_weights(weights, [])
        self._workers_table.update_data(self._get_cat_items())
        self._apply_category_ratio()

    def _get_cat_items(self) -> list:
        """当前选中分类下的工种（直接引用 trade_items 里的元素）。"""
        if not self._selected_category or not self.project_data:
            return []
        category_maps = _category_maps(self.project_data)
        return [
            ti for ti in self.project_data.get("trade_items", []) or []
            if _trade_item_category_name(ti, self.project_data, category_maps)
            == self._selected_category
        ]

    def _get_cat_indices(self) -> list[int]:
        """当前分类下每个工种在 trade_items 全局列表里的位置。"""
        if not self._selected_category or not self.project_data:
            return []
        category_maps = _category_maps(self.project_data)
        return [
            i for i, ti in enumerate(self.project_data.get("trade_items", []) or [])
            if _trade_item_category_name(ti, self.project_data, category_maps)
            == self._selected_category
        ]

    def _on_category_selected(self, name: str) -> None:
        self._selected_category = name
        self._render_workers()

    # ── 账单操作 ───────────────────────────────────────────────────────────

    def _on_bill_column_resize(self, weights: dict) -> None:
        if not self.current_uuid or self.project_data is None:
            return
        self._bill_weights = dict(weights)
        self.project_data["bill_column_widths"] = [
            {"name": k, "weight": v} for k, v in weights.items()
        ]
        self._save_bridge.schedule(self.current_uuid, self.project_data)

    def _on_worker_column_resize(self, weights: dict) -> None:
        if not self.current_uuid or self.project_data is None:
            return
        self._worker_weights = dict(weights)
        self.project_data["worker_column_widths"] = dict(weights)
        self._save_bridge.schedule(self.current_uuid, self.project_data)

    def _toggle_bill_review(self, row: int) -> None:
        if not self.project_data:
            return
        bills = self.project_data.get("bills", []) or []
        if row == -1:
            if not self._editable:
                return
            apply_bulk_review(bills)
            self._save_bridge.schedule(self.current_uuid, self.project_data)
            self._render_bills()
            return
        if row < 0 or row >= len(bills):
            return
        set_bill_reviewed(bills[row], not is_bill_reviewed(bills[row]))
        self._save_bridge.schedule(self.current_uuid, self.project_data)
        self._render_bills()

    def _sort_bills(self, column: str, order: str = "") -> None:
        if not self._editable or not self.project_data or column != "修改时间":
            return
        descending = self._bill_sort_descending
        bills = self.project_data.get("bills", []) or []
        bills.sort(key=lambda b: b.get("record_time", ""), reverse=descending)
        self.project_data["bills"] = bills
        self._save_bridge.schedule(self.current_uuid, self.project_data)
        self._bill_sort_descending = not descending
        self._bills_table.set_sort_indicator(
            "修改时间", "desc" if descending else "asc"
        )
        self._render_bills()

    def _sort_workers(self, column: str, order: str = "") -> None:
        if not self._editable or not self.project_data:
            return
        items = self.project_data.get("trade_items", [])
        if column == "单价":
            descending = self._worker_price_sort_descending
            price_positions = [
                i for i, item in enumerate(items)
                if read_billing(item).is_per_unit
            ]
            sorted_priced = sorted(
                (items[i] for i in price_positions),
                key=lambda item: read_billing(item).unit_price,
                reverse=descending,
            )
            result = list(items)
            for pos, item in zip(price_positions, sorted_priced):
                result[pos] = item
            items[:] = result
            self._worker_price_sort_descending = not descending
            self._workers_table.set_sort_indicator(
                "单价", "desc" if descending else "asc"
            )
        elif column == "计费类型":
            descending = self._worker_billing_sort_descending
            with_unit = [item for item in items if read_billing(item).is_per_unit]
            without_unit = [item for item in items if not read_billing(item).is_per_unit]
            ordered = (with_unit + without_unit) if descending else (without_unit + with_unit)
            items[:] = ordered
            self._worker_billing_sort_descending = not descending
            self._workers_table.set_sort_indicator(
                "计费类型", "desc" if descending else "asc"
            )
        else:
            return
        self._save_bridge.schedule(self.current_uuid, self.project_data)
        self._render_workers()

    def _on_bill_action(self, row: int, action: str) -> None:
        if action == "up":
            self._move_bill(row, -1)
        elif action == "down":
            self._move_bill(row, 1)
        elif action == "delete":
            self._delete_bill(row)

    def _move_bill(self, idx: int, direction: int) -> None:
        if not self._editable or not self.project_data:
            return
        bills = self.project_data.get("bills", []) or []
        target = idx + direction
        if idx < 0 or target < 0 or target >= len(bills):
            return
        bills[idx], bills[target] = bills[target], bills[idx]
        moved_id = bills[target].get("id")
        self._save_bridge.schedule(self.current_uuid, self.project_data)
        self._render_bills()
        self._select_bill_by_id(moved_id)

    def _on_bills_rows_moved(self, rows: list, target: int) -> None:
        if not self._editable or not self.project_data:
            return
        bills = self.project_data.get("bills", []) or []
        src = rows[0]
        if src < 0 or src >= len(bills):
            return
        # target 为插入下标（与 Tk _reorder_bill 的 to_idx 语义一致），
        # 直接交给 move_item，避免重复 -1 导致下移总差一行。
        to = max(0, min(target, len(bills)))
        if to == src:
            return
        moved_id = bills[src].get("id")
        self.project_data["bills"] = move_item(bills, src, to)
        self._save_bridge.schedule(self.current_uuid, self.project_data)
        self._render_bills()
        self._select_bill_by_id(moved_id)

    def _delete_bill(self, idx: int) -> None:
        if not self._editable or not self.project_data:
            return
        bills = self.project_data.get("bills", []) or []
        if idx < 0 or idx >= len(bills):
            return
        if not self._confirm_delete("确认", f"删除第 {idx + 1} 条记录？"):
            return
        bills.pop(idx)
        self._save_bridge.schedule(self.current_uuid, self.project_data)
        self._render_bills()

    def _select_bill_by_id(self, bill_id: str | None) -> None:
        if not bill_id:
            return
        bills = self.project_data.get("bills", []) or []
        for i, bill in enumerate(bills):
            if bill.get("id") == bill_id:
                self._bills_table.selectRow(i)
                return

    # ── 复制 / 粘贴：账单 ──

    def _copy_bills(self, rows: list) -> None:
        if not self.project_data:
            return
        idx = rows[0] if rows else 0
        bills = self.project_data.get("bills", []) or []
        if idx < 0 or idx >= len(bills):
            return
        bill = bills[idx]
        items = self.project_data.get("trade_items", []) or []
        cat, name = resolve_label(bill, items)
        if not name:
            snap = bill.get("frozen_snapshot")
            name = snap.get("name", "") if isinstance(snap, dict) else ""
        if not name:
            name = bill.get("trade_item_name", "")
        payload = {
            "content": bill.get("content", ""),
            "trade_item_id": bill.get("trade_item_id", ""),
            "trade_item_name_fallback": name,
        }
        for k in ("note", "work_date_type", "work_date_start",
                  "work_date_end", "frozen_snapshot", "frozen_total"):
            if bill.get(k) is not None and bill.get(k) != "":
                payload[k] = bill[k]
        self._clipboard.set_bill(payload, source_ref=self.current_uuid or "")
        self.toast.emit(f"已复制账单 #{idx + 1}（Ctrl+C）")

    def _paste_bills(self, rows: list) -> None:
        if not self.project_data or not self._editable:
            return
        if not self._clipboard.has_bill():
            return
        try:
            entry = self._clipboard.get_bill()
        except Exception as e:
            self._error_box("粘贴失败", f"剪贴板数据异常：{e}")
            return
        payload = entry["payload"]
        items = self.project_data.get("trade_items", []) or []
        new_bill = paste_bill(payload, items)
        bills = self.project_data.setdefault("bills", [])
        bills.append(new_bill)
        self._save_bridge.schedule(self.current_uuid, self.project_data)
        self._render_bills()
        if new_bill.get("trade_item_id"):
            self.toast.emit(f"已粘贴账单到末尾（新行 #{len(bills)}）（Ctrl+V）")
        else:
            self.toast.emit("已粘贴为孤儿账单（目标项目无对应工作项目）（Ctrl+V）")

    # ── 工作类型操作 ────────────────────────────────────────────────────────

    def _on_worker_action(self, row: int, action: str) -> None:
        if action == "up":
            self._move_trade_item(row, -1)
        elif action == "down":
            self._move_trade_item(row, 1)
        elif action == "delete":
            self._delete_trade_item(row)

    def _move_trade_item(self, idx: int, direction: int) -> None:
        """当前分类内上移/下移：direction=-1 上移，+1 下移。"""
        if not self._editable or not self.project_data:
            return
        cat_indices = self._get_cat_indices()
        if idx < 0 or idx >= len(cat_indices):
            return
        target = idx + direction
        if target < 0 or target >= len(cat_indices):
            return
        items = self.project_data.get("trade_items", [])
        pos_a, pos_b = cat_indices[idx], cat_indices[target]
        moved_id = items[pos_a].get("id")
        items[pos_a], items[pos_b] = items[pos_b], items[pos_a]
        self._save_bridge.schedule(self.current_uuid, self.project_data)
        self._render_workers()
        self._select_worker_by_id(moved_id)

    def _on_workers_rows_moved(self, rows: list, target: int) -> None:
        if not self._editable or not self.project_data:
            return
        cat_items = self._get_cat_items()
        src = rows[0]
        if src < 0 or src >= len(cat_items):
            return
        moved_id = cat_items[src].get("id")
        visible_ids = [item.get("id", "") for item in cat_items]
        items = self.project_data.get("trade_items", []) or []
        new_items = reorder_subset_by_ids(
            items, visible_ids, src, target,
            id_getter=lambda item: item.get("id", ""),
        )
        if new_items == items:
            return
        self.project_data["trade_items"] = new_items
        self._save_bridge.schedule(self.current_uuid, self.project_data)
        self._render_workers()
        self._select_worker_by_id(moved_id)

    def _select_worker_by_id(self, item_id: str | None) -> None:
        if not item_id:
            return
        for i, item in enumerate(self._get_cat_items()):
            if item.get("id") == item_id:
                self._workers_table.selectRow(i)
                return

    def _delete_trade_item(self, idx: int) -> None:
        """软删除工作类型：受影响账单冻结为孤儿（与 Tk 一致）。"""
        if not self._editable or not self.project_data:
            return
        cat_indices = self._get_cat_indices()
        if idx < 0 or idx >= len(cat_indices):
            return
        items = self.project_data.get("trade_items", [])
        item = items[cat_indices[idx]]
        tid = item.get("id", "")
        affected_bills = [
            b for b in self.project_data.get("bills", []) or []
            if b.get("trade_item_id") == tid
        ]
        warn_msg = f"删除「{item.get('name', '')}」？"
        if affected_bills:
            warn_msg += (
                f"\n\n有 {len(affected_bills)} 条账单引用此工作项目。"
                "删除后这些账单将显示为「已删除」并保留最后已知金额（不再随单价变化）。"
            )
        if not self._confirm_delete("确认", warn_msg):
            return
        ti_billing = read_billing(item)
        for b in affected_bills:
            b["frozen_snapshot"] = {
                "name": item.get("name", ""),
                "category": item.get("category", ""),
                "has_unit": ti_billing.has_unit,
                "unit_price": ti_billing.unit_price,
                "unit": ti_billing.unit,
            }
            b["frozen_total"] = recompute_bill_total(
                {**b.to_dict(), "trade_item_id": tid} if hasattr(b, "to_dict")
                else {**b, "trade_item_id": tid},
                items,
                self._op_map,
            )
            b["trade_item_id"] = ""
            b["_needs_attention"] = True
        del items[cat_indices[idx]]
        self._save_bridge.schedule(self.current_uuid, self.project_data)
        self._render_workers()
        self._render_bills()

    # ── 复制 / 粘贴：工作类型 ──

    def _copy_workers(self, rows: list) -> None:
        if not self.project_data:
            return
        idx = rows[0] if rows else 0
        cat_indices = self._get_cat_indices()
        if idx < 0 or idx >= len(cat_indices):
            return
        items = self.project_data.get("trade_items", []) or []
        ti = items[cat_indices[idx]]
        billing = read_billing(ti)
        payload = {
            "category": ti.get("category", ""),
            "name": ti.get("name", ""),
            "has_unit": billing.has_unit,
            "unit_price": billing.unit_price,
            "unit": billing.unit,
        }
        self._clipboard.set_trade_item(payload, source_ref=self.current_uuid or "")
        self.toast.emit(f"已复制工作「{payload['name']}」（Ctrl+C）")

    def _paste_workers(self, rows: list) -> None:
        if not self.project_data or not self._editable:
            return
        if not self._clipboard.has_trade_item():
            return
        try:
            entry = self._clipboard.get_trade_item()
        except Exception as e:
            self._error_box("粘贴失败", f"剪贴板数据异常：{e}")
            return
        payload = entry["payload"]
        items = self.project_data.get("trade_items", [])
        cat_order = self.project_data.get("category_order", []) or []
        cat_indices = self._get_cat_indices()

        idx = rows[0] if rows else None
        if idx is not None and 0 <= idx < len(cat_indices):
            global_idx = cat_indices[idx]
            target = items[global_idx]
            if self._confirm_replace(
                "确认替换",
                f"确认用剪贴板内容「{payload.get('name', '')}」替换当前行「{target.get('name', '')}」？",
            ):
                new_ti = paste_trade_item(payload, items, cat_order)
                new_ti["id"] = target["id"]
                new_ti["category"] = target["category"]
                new_ti["category_id"] = target.get("category_id", "")
                items[global_idx] = new_ti
                self._save_bridge.schedule(self.current_uuid, self.project_data)
                self._render_workers()
                self.toast.emit(f"已替换工作「{new_ti['name']}」")
            return

        # 追加到选中分类尾部（与 Tk 一致：粘贴目标 = 当前选中分类）
        cat = self._selected_category
        if not cat or cat not in cat_order:
            cat = cat_order[0] if cat_order else payload.get("category", "")
        payload["category"] = cat
        new_ti = paste_trade_item(payload, items, cat_order)
        items.append(new_ti)
        if unique_category_after_paste(new_ti["category"], cat_order):
            cat_order.append(new_ti["category"])
            self.project_data["category_order"] = cat_order
        self._save_bridge.schedule(self.current_uuid, self.project_data)
        self._render_workers()
        self.toast.emit(f"已粘贴工作「{new_ti['name']}」（Ctrl+V）")

    # ── 列显隐预设（右键账单页签）──────────────────────────────────────────

    def _show_bill_mode_menu(self) -> None:
        if not self.project_data or not self.current_uuid:
            return
        menu = QMenu(self)
        submenu = menu.addMenu(qta_icon("fa5s.columns"), "列显示")
        columns, _, hidden = resolve_bill_columns(self.project_data, self._app_config)
        data_cols = [c for c in columns if c != BILL_ACTION_COL]
        visible_set = set(data_cols) - set(hidden)

        label_action = submenu.addAction("列显示（操作列固定）")
        label_action.setEnabled(False)
        submenu.addSeparator()
        for col in data_cols:
            action = submenu.addAction(col)
            action.setCheckable(True)
            action.setChecked(col in visible_set)
            action.triggered.connect(
                lambda _=False, c=col: self._toggle_bill_column_visibility(c)
            )

        menu.addAction(qta_icon("fa5s.image"), "导出图片", self._export_image)
        menu.addSeparator()
        add_action = menu.addAction(qta_icon("fa5s.plus-circle"), "添加记录", self._add_bill)
        add_action.setEnabled(self._editable)
        menu.exec(self._tab_buttons["bills"].mapToGlobal(
            self._tab_buttons["bills"].rect().bottomLeft()
        ))

    def _show_worker_mode_menu(self) -> None:
        menu = QMenu(self)
        add_cat = menu.addAction(qta_icon("fa5s.folder-plus"), "添加分类", self._add_category)
        add_cat.setEnabled(self._editable)
        menu.addSeparator()
        restore = menu.addAction(qta_icon("fa5s.undo"), "恢复默认", self._restore_defaults)
        restore.setEnabled(self._editable)
        menu.addSeparator()
        clear = menu.addAction(qta_icon("fa5s.eraser"), "清空分类", self._clear_all_categories)
        clear.setEnabled(self._editable)
        menu.exec(self._tab_buttons["workers"].mapToGlobal(
            self._tab_buttons["workers"].rect().bottomLeft()
        ))

    def _set_bill_visible_columns(self, cols: list[str]) -> None:
        if not self.project_data or not self.current_uuid:
            return
        self.project_data["bill_visible_columns"] = list(cols)
        self._save_bridge.schedule(self.current_uuid, self.project_data)
        self._render_bills()

    def _toggle_bill_column_visibility(self, col: str) -> None:
        columns, _, hidden = resolve_bill_columns(self.project_data, self._app_config)
        visible = set(columns) - set(hidden)
        if col in visible:
            visible.discard(col)
        else:
            visible.add(col)
        ordered = [c for c in columns if c in visible]
        self._set_bill_visible_columns(ordered)

    # ── P4 业务对话框接线 ─────────────────────────────────────────────────

    def _add_bill(self) -> None:
        if not self._editable or not self.project_data:
            return
        from .dialogs import EditBillDialog
        new_bill: dict = {}
        dlg = EditBillDialog(
            self, new_bill, self.project_data, self._op_map,
            on_saved=self._on_bill_saved,
        )
        dlg.exec()

    def _edit_bill(self, row: int) -> None:
        if not self.project_data:
            return
        bills = self.project_data.get("bills", []) or []
        if row < 0 or row >= len(bills):
            return
        from .dialogs import EditBillDialog
        dlg = EditBillDialog(
            self, bills[row], self.project_data, self._op_map,
            on_saved=self._on_bill_saved,
        )
        dlg.exec()

    def _on_bill_saved(self, updated: dict) -> None:
        if not self.project_data or not self.current_uuid:
            return
        from ...project_manager import ensure_bill_id
        bills = self.project_data.get("bills", []) or []
        bill_id = updated.get("id")
        if bill_id:
            for i, b in enumerate(bills):
                if b.get("id") == bill_id:
                    bills[i] = updated
                    break
            else:
                bills.append(updated)
        else:
            ensure_bill_id(updated)
            bills.append(updated)
        self.project_data["bills"] = bills
        self._save_bridge.schedule(self.current_uuid, self.project_data)
        self._render_bills()

    def _edit_trade_item_at(self, idx: int) -> None:
        if not self._editable or not self.project_data:
            return
        cat_indices = self._get_cat_indices()
        if idx < 0 or idx >= len(cat_indices):
            return
        items = self.project_data.get("trade_items", []) or []
        ti = items[cat_indices[idx]]
        cats = _project_category_names(self.project_data)
        from .dialogs import EditTradeItemDialog
        dlg = EditTradeItemDialog(
            self, ti, cats, self._op_map,
            on_saved=self._on_trade_item_saved,
        )
        dlg.exec()

    def _on_trade_item_saved(self, updated: dict) -> None:
        if not self.project_data or not self.current_uuid:
            return
        self._save_bridge.schedule(self.current_uuid, self.project_data)
        self._render_workers()
        self._render_bills()

    def _export_image(self) -> None:
        if not self.project_data:
            return
        from .dialogs.export_image import ExportImageDialog
        dlg = ExportImageDialog(self, self.project_data, on_done=lambda: None)
        dlg.exec()

    # ── 分类管理（主-从窗格：右键菜单 / 页签菜单入口）──────────────────────

    def _on_category_menu_action(self, name: str, action: str) -> None:
        if action == "add":
            self._add_category()
        elif action == "edit":
            self._edit_category(name)
        elif action == "up":
            self._move_category(name, -1)
        elif action == "down":
            self._move_category(name, 1)
        elif action == "delete":
            self._delete_category(name)

    def _add_category(self) -> None:
        if not self._editable or not self.project_data:
            return
        name, ok = QInputDialog.getText(self, "添加工作类型", "工作类型名称：")
        if not ok:
            return
        name = name.strip()
        if not name:
            self._error_box("提示", "请输入名称")
            return
        p = self.project_data
        co = p.get("category_order", []) or []
        if name not in co:
            co.append(name)
            p["category_order"] = co
        self._save_bridge.schedule(self.current_uuid, self.project_data)
        self._selected_category = name
        self._render_workers()

    def _edit_category(self, name: str) -> None:
        if not self._editable or not self.project_data:
            return
        new_name, ok = QInputDialog.getText(self, "编辑工作类型", "工作类型名称：", text=name)
        if not ok:
            return
        new_name = new_name.strip()
        if not new_name:
            self._error_box("提示", "请输入名称")
            return
        if new_name == name:
            return
        p = self.project_data
        co = p.category_order if hasattr(p, "category_order") else p.get("category_order", []) or []
        updated = False
        for cat in co:
            if _category_name(cat) == name:
                if hasattr(cat, "name"):
                    cat.name = new_name
                elif isinstance(cat, dict):
                    cat["name"] = new_name
                else:
                    co[co.index(cat)] = new_name
                updated = True
                break
        if not updated:
            return
        for ti in p.get("trade_items", []) or []:
            if isinstance(ti, dict):
                if ti.get("category") == name:
                    ti["category"] = new_name
            elif hasattr(ti, "category") and ti.category == name:
                ti.category = new_name
        if hasattr(p, "_sync_trade_item_category_ids"):
            p._sync_trade_item_category_ids()
        self._save_bridge.schedule(self.current_uuid, self.project_data)
        self._selected_category = new_name
        self._render_workers()
        self._render_bills()

    def _move_category(self, name: str, direction: int) -> None:
        """在 category_order 中上移（-1）/下移（+1）一位，保持选中。"""
        if not self._editable or not self.project_data:
            return
        co = list(self.project_data.get("category_order", []) or [])
        if name not in co:
            return
        idx = co.index(name)
        target = idx + direction
        if target < 0 or target >= len(co):
            return
        co[idx], co[target] = co[target], co[idx]
        self.project_data["category_order"] = co
        self._save_bridge.schedule(self.current_uuid, self.project_data)
        self._render_workers()

    def _delete_category(self, name: str) -> None:
        """删除分类：所有受影响账单冻结为孤儿（与 Tk 一致）。"""
        if not self._editable or not self.project_data:
            return
        p = self.project_data
        items = p.get("trade_items", []) or []
        category_maps = _category_maps(p)
        deleting = [
            ti for ti in items
            if _trade_item_category_name(ti, p, category_maps) == name
        ]
        deleting_ids = {ti.get("id", "") for ti in deleting}
        affected_bills = [
            b for b in p.get("bills", []) or []
            if b.get("trade_item_id") in deleting_ids
        ]
        warn_msg = f"删除分类「{name}」？"
        if deleting:
            warn_msg = f"删除分类「{name}」及其所有工种？"
            if affected_bills:
                warn_msg += (
                    f"\n\n有 {len(affected_bills)} 条账单引用此分类下的工作项目，"
                    "删除后将显示为「已删除」并保留最后已知金额（不再随单价变化）。"
                )
        if not self._confirm_delete("确认", warn_msg):
            return

        if deleting:
            for ti in deleting:
                tid = ti.get("id", "")
                ti_billing = read_billing(ti)
                for b in p.get("bills", []) or []:
                    if b.get("trade_item_id") == tid:
                        b["frozen_snapshot"] = {
                            "name": ti.get("name", ""),
                            "category": _trade_item_category_name(ti, p, category_maps),
                            "has_unit": ti_billing.has_unit,
                            "unit_price": ti_billing.unit_price,
                            "unit": ti_billing.unit,
                        }
                        b["frozen_total"] = recompute_bill_total(
                            {**b.to_dict(), "trade_item_id": tid} if hasattr(b, "to_dict")
                            else {**b, "trade_item_id": tid},
                            items,
                            self._op_map,
                        )
                        b["trade_item_id"] = ""
                        b["_needs_attention"] = True

        p["trade_items"] = [
            ti for ti in items
            if _trade_item_category_name(ti, p, category_maps) != name
        ]
        co = p.get("category_order", []) or []
        p["category_order"] = [c for c in co if _category_name(c) != name]
        self._save_bridge.schedule(self.current_uuid, self.project_data)
        if self._selected_category == name:
            self._selected_category = None
        self._render_workers()
        self._render_bills()

    # ── 分类列宽比例持久化 ──────────────────────────────────────────────────

    def _on_category_splitter_moved(self, _pos: int, _index: int) -> None:
        self._category_ratio_timer.start()

    def _on_category_ratio_timeout(self) -> None:
        if not self._category_splitter or not self.current_uuid:
            return
        sizes = self._category_splitter.sizes()
        total = sizes[0] + sizes[1]
        if total <= 0:
            return
        ratio = round(sizes[0] / total, 6)
        try:
            cfg = load_app()
            old = cfg.get("category_list_width_ratio", 0)
            if abs(old - ratio) > 1e-6:
                cfg["category_list_width_ratio"] = ratio
                save_app(cfg)
        except Exception as e:
            logger.warning("[category] 保存列宽比例失败: %s", e)

    def _apply_category_ratio(self) -> None:
        if not self._category_ratio_pending or not self.current_uuid:
            return
        total = self._category_splitter.width()
        if total <= 0:
            return
        self._category_ratio_pending = False
        ratio = float(self._app_config.get("category_list_width_ratio", 0.22))
        left = int(total * ratio)
        left = max(120, min(left, max(total - 280, 120)))
        self._category_splitter.setSizes([left, max(total - left, 1)])

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

    def _clear_all_categories(self) -> None:
        """清空所有分类：移除全部工作类型，受影响账单冻结为孤儿（与 Tk 一致）。"""
        if not self._editable or not self.project_data:
            return
        p = self.project_data
        items = p.get("trade_items", []) or []
        deleting_ids = {ti.get("id", "") for ti in items}
        affected_bills = [
            b for b in p.get("bills", []) or []
            if b.get("trade_item_id") in deleting_ids
        ]
        warn_msg = "确定清空所有分类及其工作数据？此操作不可撤销。"
        if affected_bills:
            warn_msg = (
                f"有 {len(affected_bills)} 条账单引用工作项目，"
                "清空后将显示为「已删除」并保留最后已知金额（不再随单价变化）。\n\n"
                + warn_msg
            )
        if not self._confirm_delete("确认清空", warn_msg):
            return

        if items:
            category_maps = _category_maps(p)
            for ti in items:
                tid = ti.get("id", "")
                ti_billing = read_billing(ti)
                for b in p.get("bills", []) or []:
                    if b.get("trade_item_id") == tid:
                        b["frozen_snapshot"] = {
                            "name": ti.get("name", ""),
                            "category": _trade_item_category_name(ti, p, category_maps),
                            "has_unit": ti_billing.has_unit,
                            "unit_price": ti_billing.unit_price,
                            "unit": ti_billing.unit,
                        }
                        b["frozen_total"] = recompute_bill_total(
                            {**b.to_dict(), "trade_item_id": tid} if hasattr(b, "to_dict")
                            else {**b, "trade_item_id": tid},
                            items,
                            self._op_map,
                        )
                        b["trade_item_id"] = ""
                        b["_needs_attention"] = True
        p["category_order"] = []
        p["trade_items"] = []
        self._save_bridge.schedule(self.current_uuid, p)
        self._selected_category = None
        self._render_workers()
        self._render_bills()
        self.toast.emit("已清空全部分类")

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
