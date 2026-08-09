"""设置对话框（Qt）：左侧导航 + 右侧面板。

面板清单（与 Tk 版字段一致）：
  basic / font / shortcut / voice / notification / export / about。
窗口关闭时统一把各面板保存回 app_config.json（字体相关进 user_config.json）。
"""
from PySide6.QtCore import QSize, Qt
from PySide6.QtWidgets import (
    QApplication, QDialog, QHBoxLayout, QLabel, QListWidget, QListWidgetItem,
    QScrollArea, QStackedWidget, QVBoxLayout, QWidget,
)

from .....config_loader import load_app, load_user, save_user
from .....logger import logger
from ....theme import APP_BG, SIDEBAR_BG, TEXT_PRIMARY
from .basic_panel import BasicPanel
from .font_panel import FontPanel
from .shortcut_panel import ShortcutPanel
from .voice_panel import VoicePanel
from .notification_panel import NotificationPanel
from .export_panel import ExportPanel
from .about_panel import AboutPanel

_DEFAULT_SIZE = (800, 600)
_MIN_SIZE = (720, 520)

_PANELS = (
    ("basic", "基础设置", BasicPanel),
    ("font", "字体设置", FontPanel),
    ("shortcut", "快捷键", ShortcutPanel),
    ("voice", "语音播报", VoicePanel),
    ("notification", "通知", NotificationPanel),
    ("export", "导出图片", ExportPanel),
    ("about", "关于", AboutPanel),
)


class SettingsDialog(QDialog):
    """设置窗口：左列表导航 + 右堆叠面板。on_close 在窗口关闭后回调。"""

    def __init__(self, parent, on_close=None):
        super().__init__(parent)
        self._on_close_callback = on_close
        self._closed = False
        self._panels: dict[str, object] = {}
        self._panel_views: dict[str, QScrollArea] = {}
        self._panel_errors: dict[str, str] = {}
        self._current_key: str | None = None

        self.setWindowTitle("设置")
        self.setModal(True)
        self.setMinimumSize(*_MIN_SIZE)
        self.resize(*self._resolve_size())

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        title_bar = QWidget()
        title_bar.setObjectName("settingsTitleBar")
        title_bar.setFixedHeight(52)
        title_bar.setStyleSheet(
            f"QWidget#settingsTitleBar {{ background: {APP_BG}; }}"
        )
        title_layout = QHBoxLayout(title_bar)
        title_layout.setContentsMargins(20, 0, 20, 0)
        title = QLabel("⚙ 设置")
        title.setStyleSheet(
            f"color: {TEXT_PRIMARY}; font-size: 17px; font-weight: bold;"
        )
        title_layout.addWidget(title)
        layout.addWidget(title_bar)

        main = QWidget()
        main_layout = QHBoxLayout(main)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        self._nav = QListWidget()
        self._nav.setObjectName("settingsNav")
        self._nav.setFixedWidth(196)
        self._nav.setStyleSheet(
            f"QListWidget#settingsNav {{ background: {SIDEBAR_BG}; border: none; outline: none; padding: 12px 8px; }}"
            "QListWidget#settingsNav::item { padding: 8px 12px; margin: 2px 0; border-radius: 7px; }"
            "QListWidget#settingsNav::item:selected { background: #ebf5ff; color: #0060df; font-weight: bold; }"
        )
        self._nav.currentRowChanged.connect(self._on_nav_changed)
        main_layout.addWidget(self._nav)

        self._stack = QStackedWidget()
        self._stack.setObjectName("settingsStack")
        self._stack.setStyleSheet(
            f"QStackedWidget#settingsStack {{ background: {APP_BG}; border-left: 1px solid #e5e5ea; }}"
        )
        main_layout.addWidget(self._stack, 1)
        layout.addWidget(main, 1)

        self._build_nav()
        if self._nav.count():
            self._nav.setCurrentRow(0)
        else:
            self._current_key = None

    # ── 尺寸持久化 ─────────────────────────────────────────────────────

    def _resolve_size(self) -> tuple[int, int]:
        """读取设置窗口尺寸：user_config 优先 → app_config → 默认。

        只做下限 clamp；旧 Tk 版保存的逻辑像素尺寸与 Qt 同单位，
        但在小屏/高缩放环境可能超出可用屏幕，这里再按屏幕上限收敛。
        """
        for cfg in (load_user(), load_app()):
            size = (cfg.get("window_sizes") or {}).get("settings")
            if isinstance(size, list) and len(size) == 2:
                w, h = max(_MIN_SIZE[0], int(size[0])), max(_MIN_SIZE[1], int(size[1]))
                return self._clamp_to_screen(w, h)
        return _DEFAULT_SIZE

    @staticmethod
    def _clamp_to_screen(w: int, h: int) -> tuple[int, int]:
        try:
            screen = QApplication.primaryScreen()
            if screen is not None:
                area = screen.availableGeometry()
                w = min(w, max(_MIN_SIZE[0], area.width()))
                h = min(h, max(_MIN_SIZE[1], area.height()))
        except Exception:
            pass
        return w, h

    def _save_size(self) -> None:
        try:
            cfg = load_user()
            sizes = cfg.setdefault("window_sizes", {})
            sizes["settings"] = [self.width(), self.height()]
            save_user(cfg)
        except Exception as exc:
            logger.debug("[settings] 保存窗口尺寸失败: %s", exc)

    # ── 导航与面板 ─────────────────────────────────────────────────────

    def _build_nav(self) -> None:
        for key, label, _panel_cls in _PANELS:
            item = QListWidgetItem(label)
            item.setData(Qt.UserRole, key)
            # 显式设置行高：不设置时 QListWidget 会用默认 14px，
            # 文字被压扁、导航项挤成一团。
            item.setSizeHint(item.sizeHint())
            if item.sizeHint().height() <= 0:
                item.setSizeHint(QSize(0, 36))
            self._nav.addItem(item)

    def _panel_for(self, key: str):
        panel = self._panels.get(key)
        if panel is None:
            for k, _label, cls in _PANELS:
                if k == key:
                    # 面板包进滚动容器：内容超出窗口时（字体设置/快捷键等
                    # 长面板）可滚动查看，避免控件被压缩堆叠导致布局混乱。
                    scroll = QScrollArea()
                    scroll.setWidgetResizable(True)
                    scroll.setFrameShape(QScrollArea.NoFrame)
                    scroll.setStyleSheet(
                        "QScrollArea { background: transparent; border: none; }"
                    )
                    scroll.setAlignment(Qt.AlignTop)
                    self._panel_views[key] = scroll
                    try:
                        panel = cls(scroll)
                    except Exception as exc:
                        # 面板构建失败（字体枚举、配置异常等）时保持缓存为空，
                        # 下次点击可重试；_on_nav_changed 会据此拒绝切换。
                        logger.warning("[settings] 面板构建失败 (%s): %s", key, exc)
                        error_page = QWidget()
                        error_layout = QVBoxLayout(error_page)
                        error_layout.setContentsMargins(32, 32, 32, 32)
                        error_layout.setSpacing(10)
                        title = QLabel("此设置页暂时无法加载")
                        title.setStyleSheet("font-size: 17px; font-weight: bold;")
                        detail = QLabel(
                            f"页面：{dict((k, label) for k, label, _ in _PANELS).get(key, key)}\n"
                            "请重试；如果问题持续，请查看日志。"
                        )
                        detail.setWordWrap(True)
                        detail.setStyleSheet("color: #6e6e73;")
                        error_layout.addWidget(title)
                        error_layout.addWidget(detail)
                        error_layout.addStretch(1)
                        scroll.setWidget(error_page)
                        self._panel_errors[key] = str(exc)
                        self._panels[key] = None
                        self._stack.addWidget(scroll)
                        return error_page
                    scroll.setWidget(panel)
                    self._panels[key] = panel
                    self._stack.addWidget(scroll)
                    break
        return panel

    def _on_nav_changed(self, row: int) -> None:
        item = self._nav.item(row)
        if item is None:
            return
        key = item.data(Qt.UserRole)
        if key is None or key == self._current_key:
            return
        panel = self._panel_for(key)
        if panel is None:
            # 面板构建失败：不更新 current_key，否则该导航项被永久锁定，
            # 之后再点击同一项会因 key == current_key 被直接 return。
            logger.warning("[settings] 面板构建失败，导航停留在当前项: %s", key)
            return
        scroll = self._panel_views.get(key)
        if scroll is None:
            logger.warning("[settings] 未找到页面容器: %s", key)
            return
        self._current_key = key
        self._stack.setCurrentWidget(scroll)
        # 切换面板时滚回顶部，避免长面板停在上次滚动位置
        scroll.verticalScrollBar().setValue(scroll.verticalScrollBar().minimum())

    # ── 关闭 ───────────────────────────────────────────────────────────

    def closeEvent(self, event) -> None:
        if self._closed:
            event.accept()
            return
        self._closed = True
        self._flush_all()
        self._save_size()
        event.accept()
        callback = self._on_close_callback
        if callback is not None:
            try:
                callback()
            except Exception as exc:
                logger.warning("设置关闭回调执行失败: %s", exc)

    def _flush_all(self) -> None:
        for key, _label, _cls in _PANELS:
            panel = self._panels.get(key)
            if panel is None or not hasattr(panel, "save"):
                continue
            try:
                panel.save()
            except Exception as exc:
                logger.warning("设置面板保存失败 (%s): %s", key, exc)
