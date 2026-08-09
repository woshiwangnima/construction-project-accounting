"""Qt 账单表格（P3）：模型 + 视图组合，替代 Tk BillListView。

单元格格式、审核底色、孤儿红字、列宽权重、拖拽排序、右键菜单与
Tk 版保持行为一致；排序/审核切换等副作用由 QtContentArea 持久化。
"""
from qtawesome import icon as qta_icon
from PySide6.QtWidgets import QMenu

from ...logger import logger
from .table import QtBaseTable, ROW_ACTION_COLUMN
from .table_models import QtBillModel


class QtBillTable(QtBaseTable):
    def __init__(self, op_map: dict, parent=None):
        super().__init__(parent)
        self._op_map = op_map
        self._trade_items: list = []
        self._model = QtBillModel(op_map, self)
        self.bind_model(self._model)

    # ── 数据入口 ──

    def update_data(self, bills: list, trade_items: list,
                    op_map: dict | None = None, calculations=None) -> None:
        if op_map is not None:
            self._op_map = op_map
        if trade_items is not None:
            self._trade_items = list(trade_items)
        self._model.set_data(bills, self._trade_items, self._op_map, calculations)
        self._layout_pending = True
        self._apply_layout()

    def set_columns(self, columns: list[str], hidden: list[str]) -> None:
        self._model.set_columns(columns, hidden)

    # ── 右键菜单扩展：审核切换 ──

    def _extend_menu(self, menu: QMenu, rows: list[int]) -> None:
        if self._editable and len(rows) == 1:
            menu.addSeparator()
            menu.addAction(
                qta_icon("fa5s.check-circle"), "切换审核状态",
                lambda: self.review_toggle_requested.emit(rows[0]),
            )
            menu.addAction(
                qta_icon("fa5s.check-circle"), "全部标记为审核",
                lambda: self.review_toggle_requested.emit(-1),
            )
