"""ShortcutManager: global keyboard shortcut management with user customization.

Usage:
    from .shortcut_manager import shortcut_manager

    # In MainInterface.__init__:
    shortcut_manager.init(self)
    shortcut_manager.bind_all_shortcuts(self.root)

    # In context menus:
    accelerator=shortcut_manager.get_accel("add_record")
"""

import tkinter as tk

from ..logger import logger

# ── 默认快捷键定义 ────────────────────────────────────────────────────────────
# event: Tkinter 事件序列
# accel: 菜单显示文本
# label: 操作名称

DEFAULT_SHORTCUTS = {
    "new_project":     {"label": "新建项目",     "event": "<Control-n>",        "accel": "Ctrl+N"},
    "add_record":      {"label": "添加记录",     "event": "<Control-Return>",   "accel": "Ctrl+Enter"},
    "save_image":      {"label": "保存为图片",   "event": "<Control-Shift-S>",  "accel": "Ctrl+Shift+S"},
    "toggle_display":  {"label": "列显示切换",   "event": "<Alt-d>",            "accel": "Alt+D"},
    "rollback":        {"label": "回滚存档",     "event": "<F4>",               "accel": "F4"},
    "edit_project":    {"label": "编辑项目",     "event": "<Alt-e>",            "accel": "Alt+E"},
    "open_location":   {"label": "打开位置",     "event": "<Alt-f>",            "accel": "Alt+F"},
    "delete_project":  {"label": "删除项目",     "event": "<Alt-Delete>",       "accel": "Alt+Del"},
    "edit_category":   {"label": "编辑分类",     "event": "<Alt-c>",            "accel": "Alt+C"},
    "move_up":         {"label": "上移",         "event": "<Alt-Up>",           "accel": "Alt+↑"},
    "move_down":       {"label": "下移",         "event": "<Alt-Down>",         "accel": "Alt+↓"},
    "delete_category": {"label": "删除分类",     "event": "<Alt-Shift-Delete>", "accel": "Alt+Shift+Del"},
    "edit_trade":      {"label": "编辑工作",     "event": "<F2>",               "accel": "F2"},
    "delete_item":     {"label": "删除条目",     "event": "<Delete>",           "accel": "Delete"},
    "copy":            {"label": "复制",         "event": "<Control-c>",        "accel": "Ctrl+C"},
    "paste":           {"label": "粘贴",         "event": "<Control-v>",        "accel": "Ctrl+V"},
    "pin_project":     {"label": "置顶固定",     "event": "<Control-Shift-p>",  "accel": "Ctrl+Shift+P"},
}

# Action IDs grouped by context (for settings panel grouping)
ACTION_GROUPS = [
    ("通用", ("new_project", "add_record", "save_image", "toggle_display")),
    ("项目", ("edit_project", "rollback", "open_location", "delete_project", "pin_project")),
    ("分类", ("edit_category", "move_up", "move_down", "delete_category")),
    ("列表", ("edit_trade", "delete_item", "copy", "paste")),
]


class ShortcutManager:
    """Singleton shortcut manager — handles binding, dispatch, and config."""

    def __init__(self):
        self._main = None  # MainInterface reference
        self._root = None
        self._bindings: list[str] = []  # Track bound events for cleanup

    def init(self, main_interface) -> None:
        """Store MainInterface reference for action dispatch."""
        self._main = main_interface

    def _load_user_shortcuts(self) -> dict:
        """Load shortcut_settings from user_config."""
        try:
            from ..config_loader import load_user
            return load_user().get("shortcut_settings", {})
        except Exception:
            return {}

    def _load_app_shortcuts(self) -> dict:
        """Load shortcut_settings from app_config.json."""
        try:
            from ..config_loader import load_app
            return load_app().get("shortcut_settings", {})
        except Exception:
            return {}

    def get_event(self, action_id: str) -> str:
        """Return the Tkinter event string for an action (user > app_config > default)."""
        user = self._load_user_shortcuts()
        if action_id in user and "event" in user[action_id]:
            return user[action_id]["event"]
        app = self._load_app_shortcuts()
        if action_id in app and "event" in app[action_id]:
            return app[action_id]["event"]
        return DEFAULT_SHORTCUTS.get(action_id, {}).get("event", "")

    def get_accel(self, action_id: str) -> str:
        """Return the display accelerator text for a menu item (user > app_config > default)."""
        user = self._load_user_shortcuts()
        if action_id in user and "accel" in user[action_id]:
            return user[action_id]["accel"]
        app = self._load_app_shortcuts()
        if action_id in app and "accel" in app[action_id]:
            return app[action_id]["accel"]
        return DEFAULT_SHORTCUTS.get(action_id, {}).get("accel", "")

    def get_label(self, action_id: str) -> str:
        """Return the human-readable label for an action."""
        return DEFAULT_SHORTCUTS.get(action_id, {}).get("label", action_id)

    def bind_all_shortcuts(self, root: tk.Tk) -> None:
        """Bind all shortcuts globally. Call once after root is created."""
        self._root = root
        self._unbind_all()
        for action_id, defaults in DEFAULT_SHORTCUTS.items():
            event = self.get_event(action_id)
            if event:
                root.bind(event, lambda e, aid=action_id: self._dispatch(aid))
                self._bindings.append(event)
                # Also bind uppercase variant for letter keys
                if "<Control-" in event and "-Shift-" not in event:
                    upper = event.replace("<Control-", "<Control-Shift-").upper()
                    # Only add uppercase binding for simple Ctrl+letter patterns
                    if len(event) <= 18 and event[-2].isalpha():
                        upper_event = event[:-2] + event[-2].upper() + event[-1]
                        try:
                            root.bind(upper_event, lambda e, aid=action_id: self._dispatch(aid))
                            self._bindings.append(upper_event)
                        except tk.TclError:
                            pass
        logger.debug("[shortcuts] bound %d shortcuts", len(self._bindings))

    def _unbind_all(self) -> None:
        """Remove all previously bound shortcuts."""
        if not self._root:
            return
        for event in self._bindings:
            try:
                self._root.unbind(event)
            except tk.TclError:
                pass
        self._bindings.clear()

    def rebind_all(self) -> None:
        """Re-read config and rebind all shortcuts."""
        if self._root:
            self.bind_all_shortcuts(self._root)

    def _dispatch(self, action_id: str) -> None:
        """Central dispatcher for keyboard shortcuts."""
        if not self._main:
            return
        try:
            self._execute_action(action_id)
        except Exception as e:
            logger.warning("[shortcuts] dispatch '%s' failed: %s", action_id, e)

    def _execute_action(self, action_id: str) -> None:
        m = self._main
        c = m.content
        s = m.sidebar

        if action_id == "new_project":
            s._new_project()

        elif action_id == "add_record":
            if c.tab_var.get() == "bills" and c.current_uuid:
                c._add_bill()

        elif action_id == "save_image":
            if c.tab_var.get() == "bills" and c.current_uuid:
                c._export_image()

        elif action_id == "toggle_display":
            if c.tab_var.get() == "bills" and c.current_uuid:
                c._toggle_bill_display_mode()

        elif action_id == "pin_project":
            if hasattr(s, '_toggle_pin_project'):
                s._toggle_pin_project()

        elif action_id == "rollback":
            uuid = s.selected_uuid
            if uuid:
                s._open_rollback_dialog(uuid)

        elif action_id == "edit_project":
            uuid = s.selected_uuid
            if uuid:
                s._edit_project(uuid)

        elif action_id == "open_location":
            uuid = s.selected_uuid
            if uuid:
                s._open_file_location(uuid)

        elif action_id == "delete_project":
            uuid = s.selected_uuid
            if uuid:
                from ..project_manager import get_project
                project = get_project(uuid)
                if project:
                    s._delete_project(uuid, project)

        elif action_id == "edit_category":
            if c.tab_var.get() == "workers" and c.current_uuid and c._selected_category:
                c._edit_category_dialog(c._selected_category)

        elif action_id == "move_up":
            if c.tab_var.get() == "workers" and c.current_uuid and c._selected_category:
                c._move_category_up(c._selected_category)

        elif action_id == "move_down":
            if c.tab_var.get() == "workers" and c.current_uuid and c._selected_category:
                c._move_category_down(c._selected_category)

        elif action_id == "delete_category":
            if c.tab_var.get() == "workers" and c.current_uuid and c._selected_category:
                c._delete_category(c._selected_category)

        elif action_id == "edit_trade":
            if c.tab_var.get() == "workers":
                idx = c._worker_list._selected_idx if hasattr(c, '_worker_list') else None
                if idx is not None:
                    c._edit_trade_item_at(idx)

        elif action_id == "delete_item":
            if c.tab_var.get() == "workers":
                idx = c._worker_list._selected_idx if hasattr(c, '_worker_list') else None
                if idx is not None:
                    c._delete_trade_item(idx)

        elif action_id == "copy":
            tab = c.tab_var.get()
            if tab == "bills" and hasattr(c, '_bill_list'):
                c._bill_list._on_copy(c._bill_list._selected_idx)
            elif tab == "workers" and hasattr(c, '_worker_list'):
                c._worker_list._on_copy(c._worker_list._selected_idx)

        elif action_id == "paste":
            tab = c.tab_var.get()
            if tab == "bills" and hasattr(c, '_bill_list'):
                c._bill_list._on_paste(c._bill_list._selected_idx)
            elif tab == "workers" and hasattr(c, '_worker_list'):
                c._worker_list._on_paste(c._worker_list._selected_idx)

    # ── Config API ────────────────────────────────────────────────────────────

    def get_all_settings(self) -> dict:
        """Return effective shortcut settings (user > app_config > defaults)."""
        user = self._load_user_shortcuts()
        app = self._load_app_shortcuts()
        result = {}
        for action_id, defaults in DEFAULT_SHORTCUTS.items():
            app_entry = app.get(action_id, {})
            user_entry = user.get(action_id, {})
            result[action_id] = {
                "label": defaults["label"],
                "event": user_entry.get("event", app_entry.get("event", defaults["event"])),
                "accel": user_entry.get("accel", app_entry.get("accel", defaults["accel"])),
            }
        return result

    def save_settings(self, settings: dict) -> None:
        """Write shortcut_settings to user_config and rebind."""
        try:
            from ..config_loader import load_user, save_user
            cfg = load_user()
            cfg["shortcut_settings"] = settings
            save_user(cfg)
        except Exception as e:
            logger.warning("[shortcuts] save failed: %s", e)
        self.rebind_all()

    def reset_all(self) -> None:
        """Remove shortcut_settings from user_config and rebind defaults."""
        try:
            from ..config_loader import load_user, save_user
            cfg = load_user()
            cfg.pop("shortcut_settings", None)
            save_user(cfg)
        except Exception as e:
            logger.warning("[shortcuts] reset failed: %s", e)
        self.rebind_all()


# Module-level singleton
shortcut_manager = ShortcutManager()
