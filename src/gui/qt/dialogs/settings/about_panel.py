"""关于面板：版本信息 / GitHub 链接 / 更新检查 / 版本更新说明。"""
from PySide6.QtCore import Qt, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QHBoxLayout, QLabel, QMessageBox, QPlainTextEdit, QPushButton, QVBoxLayout,
)

from .....config_loader import load_app
from .....logger import logger
from .....updater import check_for_update
from .....versioning import APP_VERSION
from ....theme import (ACCENT, TEXT_PRIMARY, font_px)
from .base import BasePanel, section_hint

REPO_URL = "https://github.com/woshiwangnima/construction-project-accounting"


class ClickableLabel(QLabel):
    """点击打开链接的标签。"""

    def __init__(self, text, url: str, parent=None):
        super().__init__(text, parent)
        self._url = url

    def mousePressEvent(self, event) -> None:
        QDesktopServices.openUrl(QUrl(self._url))
        super().mousePressEvent(event)


class AboutPanel(BasePanel):
    def title_text(self) -> str:
        return "ℹ 关于"

    def hint_text(self) -> str:
        return ""

    def build(self, layout: QVBoxLayout) -> None:
        self._version = QLabel("")
        self._version.setStyleSheet(f"color: {TEXT_PRIMARY}; font-size: {font_px('body')}px;")
        layout.addWidget(self._version)

        github = ClickableLabel(f"GitHub: {REPO_URL}", REPO_URL)
        github.setStyleSheet(
            f"color: {ACCENT}; font-size: {font_px('small')}px; text-decoration: underline;"
        )
        github.setCursor(Qt.PointingHandCursor)
        layout.addWidget(github)

        check_btn = QPushButton("检查更新")
        check_btn.setProperty("secondary", True)
        check_btn.clicked.connect(self._check_update)
        layout.addWidget(check_btn)

        guide_btn = QPushButton("重新查看新手引导")
        guide_btn.setProperty("secondary", True)
        guide_btn.clicked.connect(self._replay_onboarding)
        layout.addWidget(guide_btn)

        notes_title = QLabel("版本更新说明")
        notes_title.setStyleSheet(f"font-size: {font_px('subheading')}px; font-weight: bold;")
        layout.addWidget(notes_title)

        self._notes = QPlainTextEdit()
        self._notes.setReadOnly(True)
        layout.addWidget(self._notes, 1)
        layout.addWidget(section_hint(f"当前程序版本：{APP_VERSION}（源码运行模式不检查远程更新）"))

    # ── 加载 ───────────────────────────────────────────────────────────

    def load(self) -> None:
        cfg = load_app()
        version = cfg.get("app_version") or APP_VERSION
        self._version.setText(f"当前版本：{version}")
        lines = []
        for item in cfg.get("release_notes", []) or []:
            version_text = item.get("version", "")
            date = item.get("date", "")
            lines.append(f"v{version_text}  {date}".strip())
            for note in item.get("notes", []) or []:
                lines.append(f"- {note}")
            lines.append("")
        self._notes.setPlainText("\n".join(lines).strip())

    def save(self) -> None:
        pass

    # ── 新手引导重看 ──────────────────────────────────────────────────

    def _find_main_window(self):
        """沿 parent 链找回 MainWindow（设置对话框 → 侧边栏 → 主窗口）。

        用鸭子类型（content + sidebar 属性）避免为拿一个引用而引入
        main_window 的循环导入。
        """
        obj = self.parent()
        while obj is not None:
            if hasattr(obj, "content") and hasattr(obj, "sidebar"):
                return obj
            obj = obj.parent() if hasattr(obj, "parent") else None
        return None

    def _replay_onboarding(self) -> None:
        from ...onboarding import maybe_show_onboarding

        window = self._find_main_window()
        if window is None:
            QMessageBox.warning(self, "新手引导", "找不到主窗口，无法重新播放引导。")
            return
        # 先关设置对话框：引导气泡锚在主窗口控件上，模态设置窗压在上面会挡视线。
        settings = self.window()
        if settings is not None and settings is not window:
            settings.close()
        maybe_show_onboarding(window, window.content, force=True)

    # ── 更新检查 ───────────────────────────────────────────────────────

    def _check_update(self) -> None:
        try:
            info = check_for_update()
        except Exception as exc:
            logger.warning("[about] 检查更新失败: %s", exc)
            QMessageBox.critical(self, "检查更新失败", str(exc))
            return
        if info is None:
            QMessageBox.information(self, "检查更新", "当前已是最新版本。")
            return
        notes = "\n".join(f"- {n}" for n in info.release_notes) or "- 无说明"
        QMessageBox.information(
            self,
            "发现新版本",
            f"发现新版本 v{info.version}：\n\n{notes}\n\n"
            f"下载地址：{info.download_url}",
        )
