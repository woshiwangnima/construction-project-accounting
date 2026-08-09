"""Qt 表格视图基类 + 行内操作按钮 delegate。

替代 Tk ListViewBase/RowActionButtons：QTableView + 列宽权重持久化 +
拖拽行排序 + 右键菜单（复制/粘贴/上移/下移/删除）+ 排序指示。
"""
from PySide6.QtCore import QRect, QTimer, Qt, Signal
from PySide6.QtGui import QBrush, QColor
from PySide6.QtWidgets import (
    QAbstractItemView, QHeaderView, QMenu, QStyledItemDelegate,
    QTableView, QToolTip,
)

from ...logger import logger
from ..font_manager import font_manager
from ..theme import (
    DANGER, DANGER_HOVER, HIGHLIGHT_BG, TEXT_PRIMARY, TEXT_SECONDARY,
)
from ..widgets.column_layout import ColumnSpec, capture_column_weights, compute_column_pixels

ROW_ACTION_COLUMN = "操作"


class RowActionDelegate(QStyledItemDelegate):
    """在「操作」列绘制 ↑ / ↓ / ✕ 三个小按钮。

    不拦截编辑事件：命中按钮时发射 action_triggered(row, action)。
    """

    action_triggered = Signal(int, str)

    GLYPHS = ("\u2191", "\u2193", "\u2715")
    ACTIONS = ("up", "down", "delete")
    LABELS = ("上移", "下移", "删除")
    BTN_W = 30
    PAD = 6

    def __init__(self, parent=None):
        super().__init__(parent)
        self._enabled = True
        self._hover = None  # (row, action)

    def set_enabled(self, enabled: bool) -> None:
        self._enabled = enabled

    def _button_rect(self, row_rect: QRect, idx: int) -> QRect:
        x = row_rect.x() + self.PAD + idx * (self.BTN_W + 4)
        y = row_rect.y() + (row_rect.height() - self.BTN_W) // 2
        return QRect(x, y, self.BTN_W, self.BTN_W)

    def paint(self, painter, option, index) -> None:
        painter.save()
        painter.fillRect(option.rect, option.widget.palette().base()
                         if hasattr(option.widget, "palette") else QBrush(QColor("#ffffff")))
        if self._enabled:
            for i, (glyph, action) in enumerate(zip(self.GLYPHS, self.ACTIONS)):
                r = self._button_rect(option.rect, i)
                hovered = self._hover == (index.row(), action)
                painter.setRenderHint(painter.Antialiasing)
                if hovered:
                    painter.setBrush(QColor(HIGHLIGHT_BG))
                    painter.setPen(Qt.NoPen)
                    painter.drawRoundedRect(r, 6, 6)
                if action == "delete":
                    color = DANGER_HOVER if hovered else DANGER
                else:
                    color = TEXT_PRIMARY if hovered else TEXT_SECONDARY
                painter.setPen(QColor(color))
                painter.setFont(font_manager.get("small"))
                painter.drawText(r, Qt.AlignCenter, glyph)
        painter.restore()

    def sizeHint(self, option, index):
        return option.rect.size() or index.data(Qt.SizeHintRole)

    def editorEvent(self, event, model, option, index) -> bool:
        if not self._enabled:
            return False
        if event.type() == event.Type.MouseButtonPress:
            for i, action in enumerate(self.ACTIONS):
                if self._button_rect(option.rect, i).contains(event.pos()):
                    self._hover = (index.row(), action)
                    return True
        if event.type() == event.Type.MouseButtonRelease:
            for i, action in enumerate(self.ACTIONS):
                if self._button_rect(option.rect, i).contains(event.pos()):
                    self.action_triggered.emit(index.row(), action)
                    return True
        if event.type() == event.Type.MouseMove:
            old = self._hover
            self._hover = None
            for i, action in enumerate(self.ACTIONS):
                if self._button_rect(option.rect, i).contains(event.pos()):
                    self._hover = (index.row(), action)
                    QToolTip.showText(event.globalPos(), self.LABELS[i],
                                      option.widget)
                    break
            if old != self._hover:
                index.model().dataChanged.emit(index, index)
                if self._hover is None:
                    QToolTip.hideText()
        return False


class QtBaseTable(QTableView):
    """账单/工种共用的 QTableView 封装。

    信号（由 QtContentArea 消费并持久化）：
        edit_requested(row)        双击行 → 编辑
        sort_requested(name, order) 表头点击排序
        column_resized(weights)    拖列宽结束（防抖）→ 写项目文件
        rows_moved(rows, target)   拖拽/菜单移动行
        copy_requested(rows) / paste_requested(rows)
        action_triggered(row, "up"|"down"|"delete")
    """

    edit_requested = Signal(int)
    sort_requested = Signal(str, str)
    column_resized = Signal(dict)
    rows_moved = Signal(list, int)
    copy_requested = Signal(list)
    paste_requested = Signal(list)
    action_triggered = Signal(int, str)
    review_toggle_requested = Signal(int)  # 仅账单表启用

    RESIZE_DEBOUNCE_MS = 500

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMouseTracking(True)
        self.viewport().setMouseTracking(True)
        self._action_col = ROW_ACTION_COLUMN
        self._weights: dict[str, float] = {}
        self._hidden: list[str] = []
        self._editable = True
        self._resize_timer = QTimer(self)
        self._resize_timer.setSingleShot(True)
        self._resize_timer.timeout.connect(self._emit_column_weights)
        self._layout_pending = True

        self.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.setShowGrid(False)
        self.setAlternatingRowColors(False)
        self.setDragDropMode(QAbstractItemView.InternalMove)
        self.setDragEnabled(True)
        self.setAcceptDrops(True)
        self.setDropIndicatorShown(True)
        self.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.setFocusPolicy(Qt.StrongFocus)
        self.verticalHeader().setVisible(False)
        self.verticalHeader().setDefaultSectionSize(38)
        self.horizontalHeader().setHighlightSections(False)
        self.horizontalHeader().setSortIndicatorShown(True)
        self.horizontalHeader().setSectionsClickable(True)
        self.horizontalHeader().setStyleSheet(_header_qss())

        header = self.horizontalHeader()
        header.sectionClicked.connect(self._on_section_clicked)
        header.sectionResized.connect(self._on_section_resized)
        self.clicked.connect(self._on_clicked)
        self.doubleClicked.connect(self._on_double_clicked)

    # ── 配置 ──

    def bind_model(self, model) -> None:
        self.setModel(model)
        model.rows_moved.connect(self.rows_moved)
        self._action_delegate = RowActionDelegate(self)
        self._action_delegate.action_triggered.connect(self._on_delegate_action)
        self.setItemDelegateForColumn(
            self.model().columnCount() - 1, self._action_delegate
        )

    def set_editable(self, editable: bool) -> None:
        self._editable = editable
        self.setDragEnabled(editable)
        if self.model() is not None:
            self.model().set_editable(editable)
            if self._action_delegate is not None:
                self._action_delegate.set_enabled(editable)

    def set_column_weights(self, weights: dict, hidden: list[str] | None = None) -> None:
        """应用列权重布局；隐藏列不显示（「操作」列固定显示）。"""
        model = self.model()
        if model is None:
            return
        self._weights = dict(weights)
        self._hidden = list(hidden or [])
        if self._action_col is not None and self._action_col in self._hidden:
            self._hidden.remove(self._action_col)
        self._layout_pending = True
        self._apply_layout()

    def _apply_layout(self) -> None:
        if self.model() is None:
            return
        columns = self.model()._columns
        for col, name in enumerate(columns):
            self.setColumnHidden(col, name in self._hidden and name != self._action_col)
        if not self._layout_pending or not self.isVisible():
            return
        self._layout_pending = False
        total = max(self.viewport().width(), 640)
        specs = [ColumnSpec(key=c) for c in columns]
        pixels = compute_column_pixels(specs, self._weights, total)
        header = self.horizontalHeader()
        for col, name in enumerate(columns):
            width = pixels.get(name, 80)
            if width <= 0:
                width = 80
            if name in ("日期", "改时", "修改时间") and width < 110:
                width = 110
            header.resizeSection(col, width)

    def showEvent(self, event) -> None:
        super().showEvent(event)
        if self._layout_pending:
            self._apply_layout()

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        if self._layout_pending:
            self._apply_layout()

    def _emit_column_weights(self) -> None:
        model = self.model()
        if model is None:
            return
        pixels = {c: self.columnWidth(i) for i, c in enumerate(model._columns)}
        specs = [ColumnSpec(key=c) for c in model._columns]
        weights = capture_column_weights(specs, pixels)
        self.column_resized.emit(weights)

    def _on_section_resized(self, logical_index, old_size, new_size) -> None:
        if not self._editable:
            return
        self._resize_timer.start(self.RESIZE_DEBOUNCE_MS)

    def _on_section_clicked(self, logical_index: int) -> None:
        model = self.model()
        if model is None:
            return
        if not (0 <= logical_index < len(model._columns)):
            return
        name = model._columns[logical_index]
        if name == ROW_ACTION_COLUMN:
            return
        order = "asc"
        indicator = self.horizontalHeader().sortIndicatorSection()
        if indicator == logical_index:
            order = ("desc" if self.horizontalHeader().sortIndicatorOrder()
                     == Qt.AscendingOrder else "asc")
        self.sort_requested.emit(name, order)

    def set_sort_indicator(self, column_name: str, order: str) -> None:
        model = self.model()
        if model is None:
            return
        try:
            col = model._columns.index(column_name)
        except ValueError:
            return
        self.horizontalHeader().setSortIndicator(
            col, Qt.AscendingOrder if order == "asc" else Qt.DescendingOrder)

    def _on_clicked(self, index) -> None:
        if index.isValid() and self.model() is not None:
            col = self.model()._columns[index.column()]
            if col == "审核":
                self.review_toggle_requested.emit(index.row())

    def _on_double_clicked(self, index) -> None:
        if index.isValid():
            self.edit_requested.emit(index.row())

    def _on_delegate_action(self, row: int, action: str) -> None:
        self.action_triggered.emit(row, action)

    # ── 右键菜单 ──

    def contextMenuEvent(self, event) -> None:
        if self.model() is None:
            return
        index = self.indexAt(event.pos())
        if not index.isValid():
            return
        rows = sorted({i.row() for i in self.selectedIndexes()
                       if i.row() >= 0}) or [index.row()]
        menu = QMenu(self)
        if self._editable:
            menu.addAction("\u2191 上移", lambda: self.action_triggered.emit(rows[0], "up"))
            menu.addAction("\u2193 下移", lambda: self.action_triggered.emit(rows[0], "down"))
            menu.addSeparator()
        menu.addAction("复制", lambda: self.copy_requested.emit(rows))
        menu.addAction("粘贴", lambda: self.paste_requested.emit(rows))
        self._extend_menu(menu, rows)
        menu.exec(event.globalPos())

    def _extend_menu(self, menu: QMenu, rows: list[int]) -> None:
        """子类扩展右键菜单（账单表：审核切换）。"""


def _header_qss() -> str:
    """表头局部差异：仅保留全局 QSS 未覆盖的属性（行高 padding + hover 反馈）。"""
    return (
        f"QHeaderView::section {{ padding: 8px 8px; }}"
        f"QHeaderView::section:hover {{ background: {HIGHLIGHT_BG}; }}"
    )
