import tkinter as tk
import unittest
from unittest.mock import Mock, patch

from src.gui.theme import TEXT_PRIMARY
from src.gui.widgets.bill_list_view import BillListView, ORPHAN_FG
from src.gui.widgets.worker_list_view import WorkerListView


class BillWorkerRegressionTests(unittest.TestCase):
    BILL_COLUMNS = (
        "#", "审核", "工作内容", "公式", "公式结果", "单价", "金额",
        "备注", "日期", "修改时间", "操作",
    )

    @classmethod
    def setUpClass(cls):
        try:
            cls.root = tk.Tk()
        except tk.TclError as exc:
            raise unittest.SkipTest(f"Tk display is unavailable: {exc}")
        cls.root.withdraw()

    @classmethod
    def tearDownClass(cls):
        cls.root.destroy()

    def tearDown(self):
        for child in self.root.winfo_children():
            child.destroy()
        self.root.update_idletasks()

    @staticmethod
    def _delete_state(menu):
        for index in range(menu.index(tk.END) + 1):
            if menu.type(index) == "command" and "删除" in menu.entrycget(index, "label"):
                return menu.entrycget(index, "state")
        raise AssertionError("删除菜单项不存在")

    def test_read_only_bill_delete_menu_is_disabled(self):
        view = BillListView(
            self.root,
            bills=[{"id": "b-1", "trade_item_id": "ti-1", "content": "1"}],
            trade_items=[{"id": "ti-1", "category": "A", "name": "工作", "has_unit": True, "unit_price": 1, "unit": "项"}],
            op_map={},
            columns=self.BILL_COLUMNS,
            weights={column: 1 for column in self.BILL_COLUMNS},
            hidden_cols=[],
            on_delete=Mock(),
            editable=False,
            paste_allowed=lambda: True,
        )
        menu = view._build_row_right_click_menu(0)
        self.assertEqual(self._delete_state(menu), tk.DISABLED)

    def test_read_only_worker_delete_menu_is_disabled(self):
        view = WorkerListView(
            self.root,
            items=[{"id": "ti-1", "name": "工作", "has_unit": True, "unit_price": 1, "unit": "项"}],
            on_delete=Mock(),
            editable=False,
            paste_allowed=lambda: True,
        )
        menu = view._build_row_right_click_menu(0)
        self.assertEqual(self._delete_state(menu), tk.DISABLED)

    def test_orphan_amount_uses_orphan_color_and_normal_amount_uses_text_color(self):
        view = BillListView(
            self.root,
            bills=[
                {"id": "b-1", "trade_item_id": "ti-1", "content": "2"},
                {
                    "id": "b-2",
                    "trade_item_id": "missing",
                    "content": "2",
                    "frozen_total": 4,
                    "frozen_snapshot": {"name": "已删除工作", "has_unit": True, "unit_price": 1, "unit": "项"},
                },
            ],
            trade_items=[{"id": "ti-1", "category": "A", "name": "工作", "has_unit": True, "unit_price": 3, "unit": "项"}],
            op_map={},
            columns=self.BILL_COLUMNS,
            weights={column: 1 for column in self.BILL_COLUMNS},
            hidden_cols=[],
            editable=True,
        )
        view.pack(fill=tk.BOTH, expand=True)
        self.root.update()

        self.assertEqual(view._get_row_widgets(0)["金额"].cget("fg"), TEXT_PRIMARY)
        self.assertEqual(view._get_row_widgets(1)["金额"].cget("fg"), ORPHAN_FG)


if __name__ == "__main__":
    unittest.main()
