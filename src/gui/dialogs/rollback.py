"""回滚存档弹窗。

侧边栏项目右键菜单「回滚存档」触发。
显示当前项目所有历史备份，每行带时间戳 + 存档数据有效性（孤儿账单检测）。
支持预览 + 自动备份当前状态 + 确认覆盖 三步走。
"""
import os
import shutil
import tkinter as tk
from tkinter import ttk, messagebox

from ..editability import EditabilityPolicy
from ..theme import (
    APP_BG, TEXT_PRIMARY, TEXT_SECONDARY, BORDER,
    FONT_BODY, FONT_HEADING,
)
from ..widgets import _make_btn
from ..widgets.status_badge import StatusBadge
from ..widgets.rollback_list_view import RollbackListView
from ...backup_inspector import (
        list_backups_for, BackupInfo,
        VALIDITY_OK, VALIDITY_HAS_ORPHANS, VALIDITY_INVALID_JSON,
)
from ...config_loader import load_app, load_user, save_user
from ...logger import logger
from ...project_manager import get_project, _backup_project
from ...project_uuid import project_file_path


_VALIDITY_LABELS = {
    VALIDITY_OK: "✔ 有效",
    VALIDITY_HAS_ORPHANS: "⚠ 含孤儿",
    VALIDITY_INVALID_JSON: "✗ 存档损坏",
}

_DEFAULT_ROLLBACK_SIZE = (1200, 650)
_MIN_ROLLBACK_SIZE = (900, 480)
_SAVE_RESIZE_DEBOUNCE_MS = 300


def _resolve_rollback_size() -> tuple[int, int]:
    for cfg in (load_user(), load_app()):
        size = (cfg.get("window_sizes") or {}).get("rollback")
        if isinstance(size, list) and len(size) == 2:
            return int(size[0]), int(size[1])
    return _DEFAULT_ROLLBACK_SIZE


def _save_rollback_size(w: int, h: int) -> None:
    cfg = load_user()
    sizes = cfg.setdefault("window_sizes", {})
    sizes["rollback"] = [int(w), int(h)]
    save_user(cfg)


def _format_ts(ts: str) -> str:
    if (len(ts) == 15 and ts[8] == "_"
            and ts[:8].isdigit() and ts[9:].isdigit()):
        return f"{ts[:4]}-{ts[4:6]}-{ts[6:8]} {ts[9:11]}:{ts[11:13]}:{ts[13:]}"
    if (len(ts) == 22 and ts[8] == "_" and ts[15] == "_"
            and ts[:8].isdigit() and ts[9:15].isdigit() and ts[16:].isdigit()):
        return (f"{ts[:4]}-{ts[4:6]}-{ts[6:8]} "
                f"{ts[9:11]}:{ts[11:13]}:{ts[13:15]}.{ts[16:]}")
    return ts


def _status_text_for_val(validity: str, orphan_count: int = 0) -> str:
    if validity == VALIDITY_HAS_ORPHANS:
        return f"⚠ 含 {orphan_count} 条孤儿账单"
    return _VALIDITY_LABELS.get(validity, "未知")


class RollbackDialog:
    def __init__(self, parent, project_uuid: str, on_rollback=None):
        self.project_uuid = project_uuid
        self.on_rollback = on_rollback
        self._selected_backup: BackupInfo | None = None
        self._backups: list[BackupInfo] = []
        self._project_data = get_project(project_uuid)
        project_name = (self._project_data.get("name", "未知项目")
                        if self._project_data else "未知项目")
        policy = EditabilityPolicy(
            get_current_status=None,
            current_uuid_provider=lambda: "",
        )
        project_status = policy.get_status_for(project_uuid)

        dialog = tk.Toplevel(parent)
        dialog.title("回滚存档")
        dialog.transient(parent)
        dialog.grab_set()
        dialog.configure(bg=APP_BG)
        self.dialog = dialog

        w, h = _resolve_rollback_size()
        x = parent.winfo_rootx() + (parent.winfo_width() - w) // 2
        y = parent.winfo_rooty() + (parent.winfo_height() - h) // 2
        screen_h = parent.winfo_screenheight()
        if y + h > screen_h - 40:
            y = max(20, screen_h - h - 40)
        dialog.geometry(f"{w}x{h}+{x}+{y}")
        dialog.minsize(*_MIN_ROLLBACK_SIZE)
        dialog.grid_columnconfigure(0, weight=1)
        dialog.grid_rowconfigure(1, weight=1)
        self._save_size_after_id: str | None = None
        self._initial_size = (w, h)
        dialog.bind("<Configure>", self._on_configure)

        header = tk.Frame(dialog, bg=APP_BG)
        header.grid(row=0, column=0, sticky="ew", padx=20, pady=(16, 8))

        tk.Label(
            header, text="回滚存档",
            font=FONT_HEADING, bg=APP_BG, fg=TEXT_PRIMARY,
        ).pack(anchor="w")

        info_row = tk.Frame(header, bg=APP_BG)
        info_row.pack(anchor="w", pady=(4, 0))
        tk.Label(info_row, text=f"项目：{project_name}  ",
                 font=FONT_BODY, bg=APP_BG, fg=TEXT_SECONDARY).pack(side=tk.LEFT)
        if project_status:
            StatusBadge(info_row, status=project_status, font_size=11, bg=APP_BG).pack(side=tk.LEFT)

        list_wrap = tk.Frame(dialog, bg="white", highlightbackground=BORDER, highlightthickness=1)
        list_wrap.grid(row=1, column=0, sticky="nsew", padx=20, pady=8)
        list_wrap.grid_columnconfigure(0, weight=1)
        list_wrap.grid_rowconfigure(0, weight=1)

        self._backups = list_backups_for(project_uuid)

        self._list_view = RollbackListView(
            list_wrap,
            backups=self._backups,
            on_rollback=self._confirm_from_double_click,
            on_delete_backup=self._delete_backup,
        )
        self._list_view.pack(fill=tk.BOTH, expand=True)

        if self._backups:
            self._list_view.set_selected_index(0)
            self._selected_backup = self._backups[0]

        btn_frame = tk.Frame(dialog, bg=APP_BG)
        btn_frame.grid(row=2, column=0, sticky="ew", padx=20, pady=(8, 16))
        self._rollback_btn = _make_btn(btn_frame, "回滚", self._confirm_rollback, "primary")
        self._rollback_btn.pack(side=tk.RIGHT, padx=(8, 0))
        _make_btn(btn_frame, "取消", self._close, "secondary").pack(side=tk.RIGHT)

        dialog.protocol("WM_DELETE_WINDOW", self._close)

    def _delete_backup(self, idx: int) -> None:
        if idx < 0 or idx >= len(self._backups):
            return
        backup = self._backups[idx]
        confirmed = messagebox.askyesno(
            "确认删除",
            f"确定要删除存档「{backup.path.name}」吗？\n该操作不可撤销。",
            parent=self.dialog,
        )
        if not confirmed:
            return
        try:
            os.remove(str(backup.path))
        except OSError as e:
            messagebox.showerror("错误", f"删除存档失败：{e}", parent=self.dialog)
            return
        self._backups = list_backups_for(self.project_uuid)
        self._selected_backup = self._backups[0] if self._backups else None
        items = [RollbackListView._backup_to_item(b) for b in self._backups]
        self._list_view.set_items(items)
        if self._backups:
            self._list_view.set_selected_index(0)

    def _confirm_from_double_click(self, idx: int) -> None:
        if 0 <= idx < len(self._backups):
            self._selected_backup = self._backups[idx]
        self._confirm_rollback()

    def _on_configure(self, event):
        if event.widget is not self.dialog:
            return
        if self._save_size_after_id is not None:
            try:
                self.dialog.after_cancel(self._save_size_after_id)
            except tk.TclError:
                pass
        self._save_size_after_id = self.dialog.after(_SAVE_RESIZE_DEBOUNCE_MS, self._save_size_now)

    def _save_size_now(self):
        self._save_size_after_id = None
        if not self.dialog.winfo_exists():
            return
        w, h = self.dialog.winfo_width(), self.dialog.winfo_height()
        if w < _MIN_ROLLBACK_SIZE[0] or h < _MIN_ROLLBACK_SIZE[1]:
            return
        if (w, h) == self._initial_size:
            return
        try:
            _save_rollback_size(w, h)
        except Exception as e:
            logger.warning("保存回滚窗口尺寸失败: %s", e)

    def _close(self):
        if self._save_size_after_id is not None:
            try:
                self.dialog.after_cancel(self._save_size_after_id)
            except tk.TclError:
                pass
            self._save_size_after_id = None
        self._save_size_now()
        self.dialog.destroy()

    def _confirm_rollback(self):
        if not self._backups:
            return
        sel_idx = self._list_view.get_selected_index()
        if sel_idx is None or sel_idx >= len(self._backups):
            return
        selected = self._backups[sel_idx]
        self._selected_backup = selected
        ts_display = _format_ts(selected.timestamp)

        if not self._ask_confirm_rollback(selected, ts_display):
            return

        try:
            _backup_project(self.project_uuid, force=True)
        except Exception as e:
            messagebox.showerror("错误", f"无法备份当前状态：{e}", parent=self.dialog)
            return

        try:
            src = selected.path
            dst = project_file_path(self.project_uuid)
            shutil.copy2(str(src), str(dst))
        except OSError as e:
            messagebox.showerror("错误", f"回滚失败：{e}", parent=self.dialog)
            return

        if self.on_rollback:
            try:
                self.on_rollback(self.project_uuid)
            except Exception as e:
                logger.debug("on_rollback callback raised: %s", e)
        messagebox.showinfo("成功", "项目已回滚到所选存档版本。", parent=self.dialog)
        self._close()

    def _ask_confirm_rollback(self, selected: BackupInfo, ts_display: str) -> bool:
        result = {"confirmed": False}
        popup = tk.Toplevel(self.dialog)
        popup.title("确认回滚")
        popup.transient(self.dialog)
        popup.grab_set()
        popup.configure(bg=APP_BG)
        popup.resizable(False, False)

        tk.Label(popup, text="确认回滚到所选存档？", font=FONT_HEADING,
                 bg=APP_BG, fg=TEXT_PRIMARY).pack(anchor="w", padx=20, pady=(16, 8))
        body = (
            f"备份文件：{selected.path.name}\n"
            f"备份时间：{ts_display}\n"
            f"存档有效性：{_VALIDITY_LABELS.get(selected.validity, '未知')}\n\n"
            "当前项目会先自动备份，然后再用所选存档覆盖。"
        )
        tk.Label(popup, text=body, font=FONT_BODY, bg=APP_BG, fg=TEXT_SECONDARY,
                 justify="left", wraplength=420).pack(anchor="w", padx=20, pady=(0, 12))

        btn_frame = tk.Frame(popup, bg=APP_BG)
        btn_frame.pack(fill=tk.X, padx=20, pady=(4, 16))

        def confirm():
            result["confirmed"] = True
            popup.destroy()

        _make_btn(btn_frame, "确认回滚", confirm, "danger").pack(side=tk.RIGHT, padx=(8, 0))
        _make_btn(btn_frame, "取消", popup.destroy, "secondary").pack(side=tk.RIGHT)

        popup.update_idletasks()
        w, h = popup.winfo_width(), popup.winfo_height()
        x = self.dialog.winfo_rootx() + (self.dialog.winfo_width() - w) // 2
        y = self.dialog.winfo_rooty() + (self.dialog.winfo_height() - h) // 2
        popup.geometry(f"{w}x{h}+{x}+{y}")
        self.dialog.wait_window(popup)
        return result["confirmed"]
