"""Qt 表格视图基类 + 行内操作按钮 delegate。

替代 Tk ListViewBase/RowActionButtons：QTableView + 列宽权重持久化 +
拖拽行排序 + 右键菜单（复制/粘贴/上移/下移/删除）+ 排序指示。
"""
from PySide6.QtCore import QRect, QSize, QTimer, Qt, Signal
from PySide6.QtGui import QBrush, QColor, QCursor, QFont, QFontMetrics, QPainter
from PySide6.QtWidgets import (
    QAbstractItemView, QHeaderView, QMenu, QStyle, QStyledItemDelegate,
    QTableView, QToolTip,
)

from ...logger import logger
from ..font_manager import font_manager
from ..theme import (
    APP_BG, DANGER, DANGER_HOVER, HIGHLIGHT_BG, ROW_HOVER, TEXT_PRIMARY,
    TEXT_SECONDARY,
)
from ..common.column_layout import ColumnSpec, capture_column_weights, compute_column_pixels

ROW_ACTION_COLUMN = "操作"

# 「操作」列要容纳 ↑ / ↓ / ✕ 三个按钮 + 内边距，权重再大也不该压到这个宽度以下。
_ACTION_COL_MIN_WIDTH = 112

# 各列的最小像素宽度：权重只决定“剩余空间怎么分”，这些值保证关键内容不被省略号截断。
# 金额、工作内容、操作是记账场景的核心信息，必须优先保住。
_COLUMN_MIN_WIDTHS = {
    "#": 46,
    "审核": 52,
    "工作内容": 170,
    "公式": 110,
    "公式结果": 110,
    "单价": 100,
    "金额": 134,
    "备注": 118,
    "日期": 112,
    "修改时间": 112,
    "操作": _ACTION_COL_MIN_WIDTH,
    "名称": 170,
    "单位": 68,
    "计费类型": 92,
}
_DEFAULT_COLUMN_MIN_WIDTH = 56


def column_min_width(name: str) -> int:
    """返回列的最小像素宽度，未登记的列使用默认值。"""
    return _COLUMN_MIN_WIDTHS.get(name, _DEFAULT_COLUMN_MIN_WIDTH)


class RowActionDelegate(QStyledItemDelegate):
    """在「操作」列绘制 ↑ / ↓ / ✕ 三个小按钮。

    按钮默认不绘制，只有鼠标停在某一行（``set_hover_row``）时才在该行显现，
    避免密密麻麻的图标把表格视觉压满；列宽始终保留，所以显隐不会引起列宽跳动。
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
        self._hover_row = -1  # 鼠标所在行；-1 表示鼠标不在表内

    def set_enabled(self, enabled: bool) -> None:
        self._enabled = enabled

    def set_hover_row(self, row: int) -> bool:
        """记录鼠标所在行（由 QtBaseTable 驱动）。返回是否发生变化。"""
        if self._hover_row == row:
            return False
        self._hover_row = row
        # 换行后旧的按钮级高亮不再成立，清掉免得残留高亮。
        if self._hover is not None and self._hover[0] != row:
            self._hover = None
        return True

    def is_hovered_row(self, row: int) -> bool:
        return self._enabled and row == self._hover_row

    def _button_rect(self, row_rect: QRect, idx: int) -> QRect:
        x = row_rect.x() + self.PAD + idx * (self.BTN_W + 4)
        y = row_rect.y() + (row_rect.height() - self.BTN_W) // 2
        return QRect(x, y, self.BTN_W, self.BTN_W)

    def paint(self, painter, option, index) -> None:
        painter.save()
        # PySide6 6.11 起不能再通过实例访问嵌套枚举（painter.Antialiasing 会抛
        # AttributeError，异常穿出 C++ 绘制栈后未 restore 直接段错误），
        # 必须走 QPainter.RenderHint 类级枚举。
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        # 与普通单元格保持同一套底色规则：选中 > 斑马纹/审核底色 > 悬停 > 表底。
        # 否则自定义绘制会让「操作」列变成一块突兀的白条。
        selected = bool(option.state & QStyle.State_Selected)
        row_hovered = index.row() == self._hover_row
        if selected:
            painter.fillRect(option.rect, QColor(HIGHLIGHT_BG))
        else:
            brush = index.data(Qt.BackgroundRole)
            if isinstance(brush, QBrush):
                painter.fillRect(option.rect, brush)
            elif isinstance(brush, QColor):
                painter.fillRect(option.rect, brush)
            elif row_hovered:
                painter.fillRect(option.rect, QColor(ROW_HOVER))
            else:
                base = (option.widget.palette().base()
                        if hasattr(option.widget, "palette") else QColor(APP_BG))
                painter.fillRect(option.rect, base)
        # 只有鼠标所在行才画出按钮：其余行保持空白，表格看起来干净得多。
        if self._enabled and row_hovered:
            for i, (glyph, action) in enumerate(zip(self.GLYPHS, self.ACTIONS)):
                r = self._button_rect(option.rect, i)
                hovered = self._hover == (index.row(), action)
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
        size = option.rect.size()
        if not size.isEmpty():
            return size
        fallback = index.data(Qt.SizeHintRole)
        return fallback if fallback is not None else QSize(self.BTN_W, self.BTN_W)

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
        self._action_delegate = None
        self._content_mins: dict[str, int] = {}
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
        self._rebind_action_delegate()

    def _rebind_action_delegate(self) -> None:
        """把行内操作 delegate 绑到「操作」列的真实下标。

        必须按列名反查下标：模型在构造阶段列集合为空，若沿用
        ``columnCount() - 1`` 会绑到 -1（非法列号），整列 ↑/↓/✕
        按钮都不会出现。
        """
        model = self.model()
        if model is None or self._action_delegate is None:
            return
        columns = getattr(model, "_columns", None) or []
        if self._action_col in columns:
            self.setItemDelegateForColumn(
                columns.index(self._action_col), self._action_delegate
            )

    def set_columns(self, columns: list[str], hidden: list[str] | None = None) -> None:
        """设置列集合/隐藏列，并重绑操作列 delegate。"""
        model = self.model()
        if model is None:
            return
        model.set_columns(list(columns), list(hidden or []))
        # 项目切换后旧的实测值不再适用，清空避免拿上一份数据撑列宽。
        self._content_mins = {}
        self._rebind_action_delegate()

    # ── 内容自适应列宽 ──

    # 采样行数上限：内容最小宽度按样本极值估算，避免上千行时逐格测量拖慢渲染。
    CONTENT_SAMPLE_ROWS = 120
    # 实测内容宽度的上限：防止个别超长文本把整张表挤到横向滚动。
    CONTENT_MIN_CEILING = 320
    # 单元格左右内边距 + 排序指示器占位。
    _CELL_PADDING = 28

    def measure_content_mins(self) -> None:
        """按真实单元格文本测量各列的内容最小宽度。

        静态的「最小宽度」常量只是兜底；真正决定列会不会被截断的是内容本身。
        在每次数据刷新后测量一次并缓存，``_apply_layout`` 直接取用，
        这样金额、工作内容这类关键列不会再被权重分配压到省略号。
        """
        model = self.model()
        if model is None:
            return
        columns = getattr(model, "_columns", None) or []
        if not columns:
            self._content_mins = {}
            return
        metrics = QFontMetrics(self.font())
        row_count = model.rowCount()
        step = max(1, row_count // self.CONTENT_SAMPLE_ROWS)
        measured: dict[str, int] = {}
        for col_idx, name in enumerate(columns):
            if name == self._action_col:
                continue
            # 单元格实际用的是 model 的 FontRole，与视图自身字体未必相同，
            # 必须按单元格字体测量，否则算出的宽度对不上真实绘制。
            cell_font = self._cell_font(model, col_idx, row_count)
            cell_metrics = QFontMetrics(cell_font) if cell_font is not None else metrics
            widest = cell_metrics.horizontalAdvance(name)
            for row in range(0, row_count, step):
                text = model.data(model.index(row, col_idx), Qt.DisplayRole)
                if text:
                    widest = max(widest, cell_metrics.horizontalAdvance(str(text)))
            measured[name] = widest + self._CELL_PADDING
        self._content_mins = measured

    @staticmethod
    def _cell_font(model, col_idx: int, row_count: int):
        """取该列单元格实际使用的 QFont（样本行里第一个非空 FontRole）。"""
        for row in range(min(row_count, 8)):
            font = model.data(model.index(row, col_idx), Qt.FontRole)
            if isinstance(font, QFont):
                return font
        return None

    def _content_min(self, name: str) -> int:
        """列的最小宽度 = 静态兜底与实测内容宽度取大（实测值设上限）。"""
        measured = min(self._content_mins.get(name, 0), self.CONTENT_MIN_CEILING)
        return max(column_min_width(name), measured)

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

        # 隐藏列不参与宽度分配：否则空间会分给根本不显示列，把可见列挤到截断。
        visible = [c for c in columns if c not in self._hidden or c == self._action_col]
        specs = [ColumnSpec(key=c, min_width=self._content_min(c)) for c in visible]
        weights = {k: v for k, v in self._weights.items() if k in set(visible)}
        pixels = compute_column_pixels(specs, weights, total)

        header = self.horizontalHeader()
        for col, name in enumerate(columns):
            width = pixels.get(name)
            if width is None:
                continue  # 隐藏列保持原宽度
            header.resizeSection(col, max(int(width), 1))

    def showEvent(self, event) -> None:
        super().showEvent(event)
        if self._layout_pending:
            self._apply_layout()

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        if self._layout_pending:
            self._apply_layout()

    # ── 行悬停追踪（驱动「操作」列按钮的显隐） ──

    def mouseMoveEvent(self, event) -> None:
        super().mouseMoveEvent(event)
        self._set_hover_row(self.indexAt(event.position().toPoint()).row())

    def enterEvent(self, event) -> None:
        super().enterEvent(event)
        self._sync_hover_row()

    def leaveEvent(self, event) -> None:
        super().leaveEvent(event)
        self._set_hover_row(-1)

    def wheelEvent(self, event) -> None:
        super().wheelEvent(event)
        # 滚动后鼠标没动，但鼠标底下已经换了行，必须重新取一次。
        self._sync_hover_row()

    def scrollContentsBy(self, dx: int, dy: int) -> None:
        super().scrollContentsBy(dx, dy)
        self._sync_hover_row()

    def _set_hover_row(self, row: int) -> None:
        if self._action_delegate is not None and self._action_delegate.set_hover_row(row):
            self.viewport().update()

    def _sync_hover_row(self) -> None:
        """按鼠标当前全局位置反查所在行（不依赖鼠标移动事件）。"""
        pos = self.viewport().mapFromGlobal(QCursor.pos())
        inside = self.viewport().rect().contains(pos)
        self._set_hover_row(self.indexAt(pos).row() if inside else -1)

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
