"""项目可写性中心策略（EditabilityPolicy）。

每个 App 由 `MainInterface` 持有 **唯一** 一个 `EditabilityPolicy` 实例，
然后注入到 `Sidebar` 与 `ContentArea`（以及需要写权限判断的 dialog）。

设计目的
---------
取代散落在 `content.py` / `sidebar.py` / `dialogs/*.py` 里的
`if not self._editable: ...` 与 `_set_btn_state(b, True)` 散点检查，
把这些"是否可写"的判断汇到一根管子上。

工作机制
--------
* `is_editable` 是 property，每次读取都通过注入的 `get_current_status` callable
  查"当前项目状态"——所以切换项目时自动反映新项目，不需要通知链。
* `get_status_for(project_uuid)` 按 uuid 查任意项目状态（用于回滚弹窗显示
  "该存档来自的项目当前状态"）。
* `manage(widget, normally_enabled=True)` 注册长期存在的 widget，
  立刻应用一次当前状态。
* `refresh()` 在状态切换时调用，遍历所有已注册 widget 重新应用。
* 对于按需构建的右键菜单 / 内部回调，直接读 `policy.is_editable`。
"""
from __future__ import annotations

import logging
import tkinter as tk
from tkinter import ttk
from typing import Callable, List, Optional, Tuple

from ..project_status import ProjectStatus

logger = logging.getLogger(__name__)


class EditabilityPolicy:
    """项目可写性中心策略。"""

    def __init__(self,
                 get_current_status: Callable[[], Optional[ProjectStatus]] = None,
                 current_uuid_provider: Callable[[], str] = None):
        """构造。

        Args:
            get_current_status: 返回当前项目状态的回调（用于 is_editable）。
            current_uuid_provider: 返回当前项目 uuid 的回调（用于 get_status_for 内存缓存命中）。
        """
        if get_current_status is not None and not callable(get_current_status):
            raise TypeError("get_current_status must be callable")
        if current_uuid_provider is not None and not callable(current_uuid_provider):
            raise TypeError("current_uuid_provider must be callable")
        self._get_current_status = get_current_status or (lambda: None)
        self._current_uuid_provider = current_uuid_provider or (lambda: "")
        # (widget, normally_enabled) 对
        self._managed: List[Tuple[tk.Widget, bool]] = []

    # ── 状态查询 ──

    @property
    def is_editable(self) -> bool:
        """当前选中项目是否处于"编辑中"状态。"""
        try:
            s = self._get_current_status()
        except Exception as e:
            logger.warning("get_current_status raised: %s", e)
            return True
        if s is None:
            return True
        return s.is_editable

    def get_status_for(self, project_uuid: str) -> Optional[ProjectStatus]:
        """按 UUID 查任意项目的状态。

        如果 project_uuid 等于当前项目（通过 _current_uuid_provider 拿到），
        走内存缓存（_get_current_status），不走盘。
        否则读盘（get_project(uuid) → 取 status 字段）。
        找不到 / 出错 → 返回 None。
        """
        if not project_uuid:
            return None
        # 内存缓存命中：当前项目
        current_uuid = ""
        try:
            current_uuid = self._current_uuid_provider() or ""
        except Exception as e:
            logger.debug("current_uuid_provider raised: %s", e)
        if project_uuid == current_uuid:
            try:
                return self._get_current_status()
            except Exception as e:
                logger.debug("get_current_status raised: %s", e)
        # 读盘
        try:
            from ..project_manager import get_project
            p = get_project(project_uuid)
        except Exception as e:
            logger.debug("get_project(%s) raised: %s", project_uuid, e)
            return None
        if p is None:
            return None
        return ProjectStatus.from_value(p.get("status"))

    # ── 注册 / 注销 ──

    def manage(self, widget: tk.Widget, normally_enabled: bool = True) -> None:
        """注册 widget 并立刻应用当前状态。重复注册同一 widget 是 no-op。"""
        for w, _ in self._managed:
            if w is widget:
                return
        self._managed.append((widget, normally_enabled))
        self._apply(widget, normally_enabled)

    def unmanage(self, widget: tk.Widget) -> None:
        """注销 widget（被销毁的 widget 也会在 refresh 中自动清理）。"""
        self._managed = [(w, ne) for w, ne in self._managed if w is not widget]

    def clear(self) -> None:
        """清空所有注册（一般不调用；用于测试）。"""
        self._managed.clear()

    # ── 广播刷新 ──

    def refresh(self) -> None:
        """状态切换后调用：重新评估所有已注册 widget。"""
        # 拷贝：_apply 内可能调 unmanage
        snapshot = list(self._managed)
        for w, ne in snapshot:
            if not _widget_alive(w):
                self.unmanage(w)
                continue
            self._apply(w, ne)

    # ── 内部 ──

    def _apply(self, widget: tk.Widget, normally_enabled: bool) -> None:
        """按 widget 类型应用 disabled / normal 状态。"""
        target = normally_enabled and self.is_editable
        try:
            cls_name = widget.winfo_class()
            if cls_name in ("TButton",):
                # ttk.Button
                if target:
                    widget.state(["!disabled"])
                else:
                    widget.state(["disabled"])
            elif cls_name in ("Button",):
                # tk.Button
                widget.configure(state="normal" if target else "disabled")
            elif cls_name in ("TEntry", "TCombobox"):
                # ttk 输入控件：用 state 而非 configure
                if target:
                    widget.state(["!disabled", "!readonly"])
                else:
                    widget.state(["disabled"])
            elif cls_name in ("Entry", "Combobox", "Text", "Spinbox"):
                widget.configure(state="normal" if target else "disabled")
            elif cls_name in ("Treeview",):
                # ttk.Treeview 自身没有 disabled state，用 selectmode 旁路
                widget.configure(selectmode="browse" if target else "none")
            else:
                # 兜底：尝试通用 configure(state=...)
                try:
                    widget.configure(state="normal" if target else "disabled")
                except tk.TclError:
                    logger.debug("widget %s 不支持 state 配置，跳过", cls_name)
        except tk.TclError as e:
            logger.debug("apply disabled failed on %s: %s", widget, e)
            self.unmanage(widget)


def _widget_alive(widget: tk.Widget) -> bool:
    """widget 是否还存在（未 destroy）。"""
    try:
        return bool(widget.winfo_exists())
    except tk.TclError:
        return False
