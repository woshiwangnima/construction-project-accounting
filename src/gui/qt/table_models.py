"""Qt 表格模型：账单 / 工种（替代 Tk 自绘 ListViewBase 的单元格逻辑）。

单元格格式化逻辑与 Tk bill_list_view.py / worker_list_view.py 保持一致
（公式展示、孤儿红字、审核底色、按单价/无单价等），但去 tkinter 依赖。
"""
from PySide6.QtCore import QAbstractTableModel, QModelIndex, Qt, Signal
from PySide6.QtGui import QBrush, QColor

from ...calculator import to_canonical, to_display, MathParseError
from ...billing import read_billing
from ...bill_recompute import prepare_bill_calculations
from ...bill_review import is_bill_reviewed
from ..theme import (
    APP_BG, REVIEW_BG, ROW_STRIPE, SYSTEM_GREEN, SYSTEM_RED, TEXT_PRIMARY,
    TEXT_SECONDARY, TEXT_TERTIARY,
)

# 孤儿账单行的文字色（红）+ 前缀图标（与 Tk 版一致）
ORPHAN_FG = SYSTEM_RED
ORPHAN_PREFIX = "⚠ "
BILL_SECONDARY_FG = "#5f6368"
BILL_TERTIARY_FG = "#6e6e73"


def format_formula(content_raw: str, op_map: dict) -> str:
    """将用户原始公式转为标准化展示形式；解析失败时回落原始字符串。"""
    if not content_raw:
        return ""
    try:
        return to_display(to_canonical(content_raw, op_map))
    except MathParseError:
        return content_raw


def format_bill_date(b: dict) -> str:
    """根据 bill 的 work_date_type 三态渲染为简短文本。无时间时返回空串。"""
    dt = b.get("work_date_type")
    if not dt:
        return b.get("work_date_start", "")
    if dt == "无时间":
        return ""
    if dt == "单个时间":
        return b.get("work_date_start", "")
    if dt == "起止时间":
        s = b.get("work_date_start", "")
        e = b.get("work_date_end", "")
        if s and e:
            return f"{s} ~ {e}"
        return s or e
    return ""


def bill_row_cells(idx: int, bill: dict, calc, op_map: dict) -> dict:
    """计算一行各列 (文本, 前景色, 对齐, 字体角色)。与 Tk 版逐列对齐。"""
    reviewed = is_bill_reviewed(bill)
    bg = REVIEW_BG if reviewed else (ROW_STRIPE if idx % 2 == 1 else APP_BG)
    content = bill.get("content", "")
    note = bill.get("note", "")
    date = format_bill_date(bill)

    cat, name = calc.category, calc.name
    orphan = calc.orphan
    billing = calc.billing
    total_val = calc.total

    formula_result_str = ""
    if calc.formula_value is not None:
        formula_result_str = f"{calc.formula_value:.10f}".rstrip("0").rstrip(".") or "0"

    if calc.canonical:
        formula_display = to_display(calc.canonical)
    else:
        formula_display = format_formula(content, op_map)

    if billing.is_per_unit:
        qty_str = formula_display
        price_str = billing.format_price()
    else:
        qty_str = "-"
        price_str = "无单价"

    if isinstance(total_val, (int, float)):
        total_str = f"￥{total_val:.2f}"
        total_color = ORPHAN_FG if orphan else TEXT_PRIMARY
    else:
        total_str = "错误" if content else ""
        total_color = BILL_TERTIARY_FG

    display_name = f"{ORPHAN_PREFIX}{name}" if orphan else name
    if cat and not orphan:
        display_name = f"{cat} - {name}"
    if orphan and cat:
        display_name = f"{ORPHAN_PREFIX}{cat} - {name}（已删除）"

    return {
        "#": (str(idx + 1), TEXT_PRIMARY, Qt.AlignCenter, "body"),
        "审核": ("☑" if reviewed else "☐", SYSTEM_GREEN if reviewed else BILL_TERTIARY_FG,
                 Qt.AlignCenter, "body_bold"),
        "工作内容": (display_name, ORPHAN_FG if orphan else TEXT_PRIMARY, Qt.AlignCenter, "body"),
        "公式": (qty_str, BILL_SECONDARY_FG, Qt.AlignCenter, "body"),
        "公式结果": (formula_result_str, BILL_SECONDARY_FG, Qt.AlignCenter, "body"),
        "单价": (price_str, ORPHAN_FG if orphan else TEXT_PRIMARY, Qt.AlignCenter, "body"),
        "金额": (total_str, total_color, Qt.AlignCenter, "body_bold"),
        "备注": (note, BILL_SECONDARY_FG, Qt.AlignCenter, "body"),
        "日期": (date, BILL_SECONDARY_FG, Qt.AlignCenter, "small"),
        "修改时间": (bill.get("record_time", "-"), BILL_SECONDARY_FG, Qt.AlignCenter, "small"),
    }


def worker_row_cells(item: dict) -> dict:
    """工作类型行各列 (文本, 前景色, 对齐, 字体角色)。"""
    name = item.get("name", "")
    billing = read_billing(item)
    if billing.is_per_unit:
        price_text = f"￥{billing.unit_price:.2f}"
        unit_text = billing.unit
        billing_text = "按单价"
        billing_color = TEXT_SECONDARY
    else:
        price_text = "-"
        unit_text = "-"
        billing_text = "无单价"
        billing_color = TEXT_TERTIARY
    return {
        "名称": (name, TEXT_PRIMARY, Qt.AlignCenter, "body"),
        "单价": (price_text, TEXT_PRIMARY, Qt.AlignCenter, "body_bold"),
        "单位": (unit_text, TEXT_PRIMARY, Qt.AlignCenter, "body"),
        "计费类型": (billing_text, billing_color, Qt.AlignCenter, "body"),
    }


class _RowTableModel(QAbstractTableModel):
    """QAbstractTableModel 基类：列集合 + 行单元格缓存 + 拖拽行排序。"""

    MIME_TYPE = "application/x-cpa-rows"
    rows_moved = Signal(list, int)  # (源行号列表, 目标行号)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._columns: list[str] = []
        self._hidden: set[str] = set()
        self._editable = True
        self._rows: list = []
        self._cache: dict[int, dict] = {}

    # ── 配置 ──
    def set_columns(self, columns: list[str], hidden_cols: list[str]) -> None:
        self._columns = list(columns)
        self._hidden = set(hidden_cols)
        self._cache.clear()
        self.beginResetModel()
        self.endResetModel()

    def set_editable(self, editable: bool) -> None:
        self._editable = editable

    # ── QAbstractTableModel 接口 ──
    def rowCount(self, parent=QModelIndex()) -> int:
        return 0 if parent.isValid() else len(self._rows)

    def columnCount(self, parent=QModelIndex()) -> int:
        return 0 if parent.isValid() else len(self._columns)

    def headerData(self, section, orientation, role=Qt.DisplayRole):
        if orientation == Qt.Horizontal and role == Qt.DisplayRole:
            if 0 <= section < len(self._columns):
                return self._columns[section]
        return None

    def flags(self, index):
        if not index.isValid():
            return Qt.ItemIsEnabled
        base = Qt.ItemIsEnabled | Qt.ItemIsSelectable | Qt.ItemIsDropEnabled
        if self._editable:
            base |= Qt.ItemIsDragEnabled
        return base

    def mimeTypes(self):
        return [self.MIME_TYPE]

    def mimeData(self, indexes):
        from PySide6.QtCore import QMimeData
        rows = sorted({i.row() for i in indexes if i.isValid()})
        if not rows:
            return None
        data = QMimeData()
        data.setData(self.MIME_TYPE, ",".join(str(r) for r in rows).encode())
        return data

    def supportedDropActions(self):
        return Qt.MoveAction

    def dropMimeData(self, data, action, row, column, parent):
        if action == Qt.IgnoreAction or not data.hasFormat(self.MIME_TYPE):
            return False
        src_rows = [int(r) for r in data.data(self.MIME_TYPE).decode().split(",")]
        target = row if row >= 0 else (parent.row() if parent.isValid() else self.rowCount())
        self.rows_moved.emit(src_rows, target)
        return True

    # ── 行数据缓存 ──
    def _invalidate(self) -> None:
        self._cache.clear()
        self.beginResetModel()
        self.endResetModel()


class QtBillModel(_RowTableModel):
    """账单模型：格式化 + 审核底色 + 孤儿红字。"""

    def __init__(self, op_map: dict, parent=None):
        super().__init__(parent)
        self._op_map = op_map
        self._trade_items: list = []
        self._calculations: list = []

    def set_data(self, bills: list, trade_items: list | None = None,
                 op_map: dict | None = None, calculations=None) -> None:
        self._rows = list(bills or [])
        if op_map is not None:
            self._op_map = op_map
        if trade_items is not None:
            self._trade_items = list(trade_items or [])
        if calculations is None or len(calculations) != len(self._rows):
            self._calculations = prepare_bill_calculations(
                self._rows, self._trade_items, self._op_map
            )
        else:
            self._calculations = list(calculations)
        self._invalidate()

    def row_cells(self, row: int) -> dict:
        cells = self._cache.get(row)
        if cells is None:
            cells = bill_row_cells(
                row, self._rows[row], self._calculations[row], self._op_map
            )
            cells["_bg"] = cells.get("_bg") or (
                REVIEW_BG if is_bill_reviewed(self._rows[row])
                else (ROW_STRIPE if row % 2 == 1 else APP_BG)
            )
            self._cache[row] = cells
        return cells

    def data(self, index, role=Qt.DisplayRole):
        if not index.isValid() or not (0 <= index.row() < len(self._rows)):
            return None
        col = self._columns[index.column()]
        cells = self.row_cells(index.row())
        if role == Qt.DisplayRole or role == Qt.EditRole:
            return cells.get(col, (None, None, None, None))[0]
        if role == Qt.ForegroundRole:
            color = cells.get(col, (None, None, None, None))[1]
            return QColor(color) if color else None
        if role == Qt.TextAlignmentRole:
            return cells.get(col, (None, None, None, None))[2]
        if role == Qt.FontRole:
            font_role = cells.get(col, (None, None, None, "body"))[3]
            return _role_font(font_role)
        if role == Qt.BackgroundRole:
            bg = cells["_bg"]
            return QBrush(QColor(bg)) if bg else None
        if role == Qt.ToolTipRole:
            if col == "公式":
                return str(self._rows[index.row()].get("content", ""))
        return None


class QtWorkerModel(_RowTableModel):
    """工作类型模型。"""

    def set_data(self, items: list) -> None:
        self._rows = list(items or [])
        self._invalidate()

    def data(self, index, role=Qt.DisplayRole):
        if not index.isValid() or not (0 <= index.row() < len(self._rows)):
            return None
        col = self._columns[index.column()]
        if role == Qt.DisplayRole or role == Qt.EditRole:
            return worker_row_cells(self._rows[index.row()]).get(col, (None, None, None, None))[0]
        if role == Qt.ForegroundRole:
            color = worker_row_cells(self._rows[index.row()]).get(col, (None, None, None, None))[1]
            return QColor(color) if color else None
        if role == Qt.TextAlignmentRole:
            return worker_row_cells(self._rows[index.row()]).get(col, (None, None, None, None))[2]
        if role == Qt.FontRole:
            font_role = worker_row_cells(self._rows[index.row()]).get(col, (None, None, None, "body"))[3]
            return _role_font(font_role)
        if role == Qt.BackgroundRole:
            bg = ROW_STRIPE if index.row() % 2 == 1 else APP_BG
            return QBrush(QColor(bg)) if bg else None
        return None


_role_font_cache = {}


def _role_font(role: str):
    """按字体角色返回 QFont（缓存，避免每格新建）。"""
    font = _role_font_cache.get(role)
    if font is None:
        from ..font_manager import font_manager
        font = font_manager.get(role)
        _role_font_cache[role] = font
    return font
