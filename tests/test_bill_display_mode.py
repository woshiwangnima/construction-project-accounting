import unittest

from src.config_loader import _DEFAULT_CONFIGS, _repair_column_flags
from src.gui.qt.category_utils import BILL_ACTION_COL, resolve_bill_columns
from src.gui.qt.dialogs.confirm import _resolve_parent
from src.project import Project


APP_CONFIG = {
    "default_bill_column_widths_data": [
        {"name": "#",       "weight": 0.05, "show_in_simple": True,  "show_in_audit": False},
        {"name": "工作内容", "weight": 0.40, "show_in_simple": True,  "show_in_audit": True},
        {"name": "公式结果", "weight": 0.25, "show_in_simple": False, "show_in_audit": True},
        {"name": "日期",     "weight": 0.20, "show_in_simple": False, "show_in_audit": True},
        {"name": "修改时间", "weight": 0.05, "show_in_simple": False, "show_in_audit": False},
        {"name": BILL_ACTION_COL, "weight": 0.05, "show_in_simple": True, "show_in_audit": True},
    ]
}


def _hidden(project_data) -> list[str]:
    return resolve_bill_columns(project_data, APP_CONFIG)[2]


class ProjectDelItemTests(unittest.TestCase):
    """Project 是 dataclass，但对外充当 mapping；删除语义 = 重置为字段缺省值。"""

    def setUp(self):
        self.project = Project.from_dict({"project_uuid": "p1", "name": "T"})

    def test_deleting_a_list_field_resets_it_to_an_empty_list(self):
        self.project["bill_visible_columns"] = ["工作内容"]

        del self.project["bill_visible_columns"]

        self.assertEqual(self.project.bill_visible_columns, [])

    def test_deleting_a_scalar_field_restores_the_dataclass_default(self):
        self.project["bill_display_mode"] = "audit"

        del self.project["bill_display_mode"]

        self.assertEqual(self.project.bill_display_mode, "simple")

    def test_unknown_key_raises_key_error(self):
        with self.assertRaises(KeyError):
            del self.project["没有这个字段"]

    def test_path_alias_is_a_no_op(self):
        del self.project["_path"]

    def test_deleted_field_still_reports_as_contained(self):
        # __contains__ 基于 hasattr，删除只是重置，键依然存在——调用方要按值判断
        del self.project["bill_visible_columns"]

        self.assertIn("bill_visible_columns", self.project)


class BillDisplayModeTests(unittest.TestCase):
    def test_each_mode_hides_a_different_set_of_columns(self):
        simple = _hidden({"bill_display_mode": "simple"})
        audit = _hidden({"bill_display_mode": "audit"})
        everything = _hidden({"bill_display_mode": "complex"})

        self.assertEqual(sorted(simple), sorted(["公式结果", "日期", "修改时间"]))
        self.assertEqual(sorted(audit), sorted(["#", "修改时间"]))
        self.assertEqual(everything, [])
        self.assertNotEqual(simple, audit)

    def test_operation_column_is_never_auto_hidden(self):
        for mode in ("simple", "audit", "complex"):
            with self.subTest(mode=mode):
                self.assertNotIn(BILL_ACTION_COL, _hidden({"bill_display_mode": mode}))

    def test_unknown_mode_falls_back_to_showing_everything(self):
        self.assertEqual(_hidden({"bill_display_mode": "nope"}), [])

    def test_missing_mode_defaults_to_simple(self):
        self.assertEqual(sorted(_hidden({})), sorted(["公式结果", "日期", "修改时间"]))

    def test_explicit_visible_columns_win_over_the_mode(self):
        hidden = _hidden({"bill_display_mode": "complex", "bill_visible_columns": ["工作内容", "日期"]})

        self.assertEqual(sorted(hidden), sorted(["#", "公式结果", "修改时间"]))

    def test_hidden_weights_are_redistributed_to_visible_columns(self):
        _, weights, hidden = resolve_bill_columns({"bill_display_mode": "audit"}, APP_CONFIG)

        self.assertEqual(sorted(hidden), sorted(["#", "修改时间"]))
        self.assertGreater(weights["工作内容"], APP_CONFIG["default_bill_column_widths_data"][1]["weight"])


class SwitchBillModeRegressionTests(unittest.TestCase):
    """回归：_switch_bill_mode 会 del project["bill_visible_columns"]。

    Project 缺 __delitem__ 时这里抛 AttributeError，模式切换在
    「保存 + 重绘」之前就中断，三个按钮看起来全都没反应。
    """

    def test_switching_mode_clears_the_explicit_column_list(self):
        project = Project.from_dict({
            "project_uuid": "p1",
            "name": "T",
            "bill_display_mode": "complex",
            "bill_visible_columns": ["工作内容"],
        })

        project["bill_display_mode"] = "audit"
        del project["bill_visible_columns"]

        self.assertEqual(project.bill_visible_columns, [])
        self.assertEqual(sorted(_hidden(project)), sorted(["#", "修改时间"]))

    def test_every_mode_reaches_a_distinct_visible_state_after_switching(self):
        project = Project.from_dict({
            "project_uuid": "p1",
            "name": "T",
            "bill_visible_columns": ["工作内容"],
        })
        seen = {}
        for mode in ("simple", "audit", "complex"):
            project["bill_display_mode"] = mode
            del project["bill_visible_columns"]
            seen[mode] = tuple(sorted(_hidden(project)))

        self.assertEqual(len(set(seen.values())), 3)


class LegacyColumnFlagRepairTests(unittest.TestCase):
    """回归：旧配置的行只有 show_in_simple，缺 show_in_audit。

    default_bill_column_widths_data 是列表，_deep_merge 整体替换而非逐行合并，
    所以老配置永远不会自动获得新标记，「查账模式」因此与「显示全部」无异。
    """

    def setUp(self):
        self.defaults = _DEFAULT_CONFIGS["app_config.json"]["default_bill_column_widths_data"]

    def test_code_defaults_define_both_mode_flags_for_every_column(self):
        for row in self.defaults:
            with self.subTest(column=row["name"]):
                self.assertIn("show_in_simple", row)
                self.assertIn("show_in_audit", row)

    def test_missing_audit_flag_is_backfilled_from_defaults(self):
        legacy = [{"name": d["name"], "weight": d["weight"], "show_in_simple": d["show_in_simple"]}
                  for d in self.defaults]

        repaired = _repair_column_flags(legacy, self.defaults)

        for row in repaired:
            self.assertIn("show_in_audit", row)
        audit_hidden = [r["name"] for r in repaired if not r["show_in_audit"]]
        self.assertEqual(sorted(audit_hidden), sorted(["#", "修改时间"]))

    def test_explicit_user_values_are_not_overwritten(self):
        legacy = [{"name": "#", "weight": 0.9, "show_in_simple": False, "show_in_audit": True}]

        repaired = _repair_column_flags(legacy, self.defaults)

        self.assertEqual(repaired[0]["weight"], 0.9)
        self.assertIs(repaired[0]["show_in_simple"], False)
        self.assertIs(repaired[0]["show_in_audit"], True)

    def test_unknown_columns_pass_through_untouched(self):
        custom = [{"name": "自定义列", "weight": 0.5}]

        self.assertEqual(_repair_column_flags(custom, self.defaults), custom)

    def test_non_dict_rows_are_left_alone(self):
        self.assertEqual(_repair_column_flags(["脏数据"], self.defaults), ["脏数据"])

    def test_legacy_config_yields_three_distinct_modes_after_repair(self):
        legacy = [{"name": d["name"], "weight": d["weight"], "show_in_simple": d["show_in_simple"]}
                  for d in self.defaults]
        cfg = {"default_bill_column_widths_data": _repair_column_flags(legacy, self.defaults)}

        seen = {
            mode: tuple(sorted(resolve_bill_columns({"bill_display_mode": mode}, cfg)[2]))
            for mode in ("simple", "audit", "complex")
        }

        self.assertEqual(len(set(seen.values())), 3)
        self.assertIn("#", seen["audit"])


class ConfirmDialogParentTests(unittest.TestCase):
    """回归：qfluentwidgets 的遮罩尺寸取自 parent，传窄控件会把对话框裁掉。"""

    class _Widget:
        def __init__(self, window):
            self._window = window

        def window(self):
            return self._window

    class _TopLevel:
        pass

    def test_child_widget_is_promoted_to_its_top_level_window(self):
        top = self._TopLevel()

        self.assertIs(_resolve_parent(self._Widget(top)), top)

    def test_a_top_level_widget_resolves_to_itself(self):
        top = self._TopLevel()
        top.window = lambda: top

        self.assertIs(_resolve_parent(top), top)

    def test_none_stays_none_so_the_qmessagebox_fallback_can_trigger(self):
        self.assertIsNone(_resolve_parent(None))

    def test_object_without_window_is_used_as_is(self):
        plain = object()

        self.assertIs(_resolve_parent(plain), plain)


if __name__ == "__main__":
    unittest.main()
