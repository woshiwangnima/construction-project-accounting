"""回滚存档对话框（Qt）。

左侧列出项目的所有历史备份，右侧显示所选备份的差异摘要
（备份时间 / 文件大小 / 条目数 / 有效性 / 孤儿账单 / 工作数量情况）。
确认回滚前先自动备份当前状态，再二次确认，最后用所选存档覆盖项目文件。
"""
import shutil

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog, QFrame, QHBoxLayout, QLabel, QListWidget, QListWidgetItem,
    QMessageBox, QPushButton, QVBoxLayout, QWidget,
)

from ....backup_inspector import (
    list_backups_for, BackupInfo,
    VALIDITY_OK, VALIDITY_HAS_ORPHANS, VALIDITY_INVALID_JSON,
)
from ....config_loader import load_app, load_user
from ....logger import logger
from ....project_manager import get_project, _backup_project
from ....project_uuid import project_file_path
from ...theme import BORDER, TEXT_SECONDARY
from .confirm import confirm_dialog

_VALIDITY_LABELS = {
    VALIDITY_OK: "✔ 有效",
    VALIDITY_HAS_ORPHANS: "⚠ 含孤儿",
    VALIDITY_INVALID_JSON: "✗ 存档损坏",
}

_DEFAULT_SIZE = (980, 560)
_MIN_SIZE = (760, 440)


def _format_ts(ts: str) -> str:
    if (len(ts) == 15 and ts[8] == "_"
            and ts[:8].isdigit() and ts[9:].isdigit()):
        return f"{ts[:4]}-{ts[4:6]}-{ts[6:8]} {ts[9:11]}:{ts[11:13]}:{ts[13:]}"
    if (len(ts) == 22 and ts[8] == "_" and ts[15] == "_"
            and ts[:8].isdigit() and ts[9:15].isdigit() and ts[16:].isdigit()):
        return (f"{ts[:4]}-{ts[4:6]}-{ts[6:8]} "
                f"{ts[9:11]}:{ts[11:13]}:{ts[13:15]}.{ts[16:]}")
    return ts


def _format_size(size: int) -> str:
    try:
        size = int(size)
    except (TypeError, ValueError):
        return "-"
    if size < 1024:
        return f"{size} B"
    if size < 1024 * 1024:
        return f"{size / 1024:.1f} KB"
    return f"{size / 1024 / 1024:.2f} MB"


def _validity_text(backup: BackupInfo) -> str:
    if backup.validity == VALIDITY_HAS_ORPHANS:
        return f"⚠ 含 {backup.orphan_count} 条孤儿账单"
    return _VALIDITY_LABELS.get(backup.validity, "未知")


class RollbackDialog(QDialog):
    """项目回滚存档对话框。on_rollback(uuid) 在回滚成功后回调。"""

    def __init__(self, parent, project_uuid: str, on_rollback=None):
        super().__init__(parent)
        self.project_uuid = project_uuid
        self.on_rollback = on_rollback
        self._backups: list[BackupInfo] = []
        self._selected: BackupInfo | None = None

        project = get_project(project_uuid)
        project_name = (project.get("name", "未知项目")
                        if project is not None else "未知项目")

        self.setWindowTitle("回滚存档")
        self.setModal(True)
        self.setMinimumSize(*_MIN_SIZE)
        self.resize(*self._resolve_size())

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 16, 20, 16)
        layout.setSpacing(10)

        title = QLabel("回滚存档")
        title.setStyleSheet("font-size: 18px; font-weight: bold;")
        layout.addWidget(title)

        info = QLabel(f"项目：{project_name}")
        info.setStyleSheet(f"color: {TEXT_SECONDARY};")
        layout.addWidget(info)

        split = QWidget()
        split_layout = QHBoxLayout(split)
        split_layout.setContentsMargins(0, 0, 0, 0)
        split_layout.setSpacing(12)

        # ── 左侧：备份列表 ──
        list_card = QFrame()
        list_card.setStyleSheet(
            f"background: #ffffff; border: 1px solid {BORDER}; border-radius: 8px;"
        )
        list_card_layout = QVBoxLayout(list_card)
        list_card_layout.setContentsMargins(8, 8, 8, 8)
        self._list = QListWidget()
        self._list.currentRowChanged.connect(self._on_select)
        list_card_layout.addWidget(self._list)
        split_layout.addWidget(list_card, 2)

        # ── 右侧：摘要 ──
        summary_card = QFrame()
        summary_card.setStyleSheet(
            f"background: #ffffff; border: 1px solid {BORDER}; border-radius: 8px;"
        )
        summary_layout = QVBoxLayout(summary_card)
        summary_layout.setContentsMargins(14, 12, 14, 12)
        summary_layout.setSpacing(8)

        summary_title = QLabel("存档摘要")
        summary_title.setStyleSheet("font-size: 15px; font-weight: bold;")
        summary_layout.addWidget(summary_title)

        self._summary_labels: dict[str, QLabel] = {}
        for key, label in (
            ("time", "备份时间"),
            ("size", "文件大小"),
            ("validity", "存档有效性"),
            ("bills", "账单数"),
            ("trades", "工作数量情况"),
            ("file", "备份文件"),
        ):
            row = QHBoxLayout()
            name = QLabel(label)
            name.setStyleSheet(f"color: {TEXT_SECONDARY};")
            name.setFixedWidth(90)
            value = QLabel("-")
            value.setWordWrap(True)
            value.setTextInteractionFlags(Qt.TextSelectableByMouse)
            row.addWidget(name)
            row.addWidget(value, 1)
            summary_layout.addLayout(row)
            self._summary_labels[key] = value

        summary_layout.addStretch(1)
        split_layout.addWidget(summary_card, 3)
        layout.addWidget(split, 1)

        # ── 底部按钮 ──
        btn_row = QHBoxLayout()
        btn_row.addStretch(1)
        self._rollback_btn = QPushButton("回滚")
        self._rollback_btn.clicked.connect(self._confirm_rollback)
        self._rollback_btn.setEnabled(False)
        btn_row.addWidget(self._rollback_btn)
        cancel_btn = QPushButton("取消")
        cancel_btn.setProperty("secondary", True)
        cancel_btn.clicked.connect(self.reject)
        btn_row.addWidget(cancel_btn)
        layout.addLayout(btn_row)

        self._backups = list_backups_for(project_uuid)
        self._refresh_list()

    # ── 尺寸持久化 ─────────────────────────────────────────────────────

    def _resolve_size(self) -> tuple[int, int]:
        for cfg in (load_user(), load_app()):
            size = (cfg.get("window_sizes") or {}).get("rollback")
            if isinstance(size, list) and len(size) == 2:
                return int(size[0]), int(size[1])
        return _DEFAULT_SIZE

    def _save_size(self) -> None:
        try:
            cfg = load_user()
            sizes = cfg.setdefault("window_sizes", {})
            sizes["rollback"] = [self.width(), self.height()]
            from ....config_loader import save_user
            save_user(cfg)
        except Exception as exc:
            logger.debug("[rollback] 保存窗口尺寸失败: %s", exc)

    def closeEvent(self, event) -> None:
        self._save_size()
        super().closeEvent(event)

    # ── 列表与摘要 ─────────────────────────────────────────────────────

    def _refresh_list(self) -> None:
        self._list.clear()
        for backup in self._backups:
            text = _format_ts(backup.timestamp)
            if backup.validity != VALIDITY_OK:
                text += f"  {_validity_text(backup)}"
            item = QListWidgetItem(text)
            item.setToolTip(str(backup.path))
            self._list.addItem(item)
        if self._backups:
            self._list.setCurrentRow(0)
        else:
            self._summary_labels["time"].setText("（无备份存档）")
            self._rollback_btn.setEnabled(False)

    def _on_select(self, row: int) -> None:
        if row < 0 or row >= len(self._backups):
            self._selected = None
            self._rollback_btn.setEnabled(False)
            return
        backup = self._backups[row]
        self._selected = backup
        self._rollback_btn.setEnabled(True)
        self._summary_labels["time"].setText(_format_ts(backup.timestamp))
        self._summary_labels["size"].setText(_format_size(_stat_size(backup)))
        self._summary_labels["validity"].setText(_validity_text(backup))
        self._summary_labels["bills"].setText(backup.bill_summary)
        self._summary_labels["trades"].setText(backup.trade_summary)
        self._summary_labels["file"].setText(backup.path.name)

    # ── 回滚流程 ───────────────────────────────────────────────────────

    def _confirm_rollback(self) -> None:
        backup = self._selected
        if backup is None:
            return
        ts_display = _format_ts(backup.timestamp)
        body = (
            f"备份文件：{backup.path.name}\n"
            f"备份时间：{ts_display}\n"
            f"存档有效性：{_VALIDITY_LABELS.get(backup.validity, '未知')}\n\n"
            "当前项目会先自动备份，然后再用所选存档覆盖。"
        )
        if not confirm_dialog(self, "确认回滚", body, default_yes=False):
            return

        try:
            _backup_project(self.project_uuid, force=True)
        except Exception as exc:
            logger.warning("[rollback] 备份当前状态失败: %s", exc)
            QMessageBox.critical(self, "错误", f"无法备份当前状态：{exc}")
            return

        try:
            dst = project_file_path(self.project_uuid)
            shutil.copy2(str(backup.path), str(dst))
        except OSError as exc:
            logger.warning("[rollback] 覆盖项目文件失败: %s", exc)
            QMessageBox.critical(self, "错误", f"回滚失败：{exc}")
            return

        if self.on_rollback is not None:
            try:
                self.on_rollback(self.project_uuid)
            except Exception as exc:
                logger.debug("[rollback] on_rollback callback raised: %s", exc)

        QMessageBox.information(self, "成功", "项目已回滚到所选存档版本。")
        self.accept()


def _stat_size(backup: BackupInfo) -> int:
    try:
        return backup.path.stat().st_size
    except OSError:
        return 0
