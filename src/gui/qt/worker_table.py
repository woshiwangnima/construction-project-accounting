"""Qt 工作类型表格（P3）：替代 Tk WorkerListView（ttk.Treeview）。

单价/单位/计费类型列 + 操作按钮列，与 Tk 版列定义一致
（WORKER_COLUMNS 顺序: 名称/单价/单位/计费类型/操作）。
"""
from .table import QtBaseTable
from .table_models import QtWorkerModel


class QtWorkerTable(QtBaseTable):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._model = QtWorkerModel(self)
        self.bind_model(self._model)

    def update_data(self, items: list) -> None:
        self._model.set_data(items)
        self.measure_content_mins()
        self._layout_pending = True
        self._apply_layout()
