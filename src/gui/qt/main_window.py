"""Qt 主窗口（替代 Tk MainInterface）。

P2 范围：窗口几何持久化（JSON window_sizes.main）、QSplitter 侧栏比例、
全局 QSS + 字体、快捷键绑定、更新检查（发现结果仅记日志，P4 接对话框）。
"""
from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QSplitter, QVBoxLayout, QWidget,
)

from ...logger import logger
from ...config_loader import load_app, save_app
from ...updater import UpdateChecker
from ...voice import get_voice
from ..editability import EditabilityPolicy
from ..font_manager import font_manager
from ..theme import build_qss
from .. import shortcut_manager as sm_module
from .sidebar import QtSidebar
from .content import QtContentArea

sm = sm_module.shortcut_manager


class MainWindow(QMainWindow):
    WINDOW_KEY = "main"

    def __init__(self):
        super().__init__()
        self._closed = False
        self._save_after_id = None
        self._update_check_after_id = None
        self._update_poll_after_id = None
        self._update_checker = None
        self._update_check_running = False

        self.setWindowTitle("施工项目记账程序")
        self.setMinimumSize(1000, 650)

        # 字体与样式必须先于任何控件构建
        font_manager.init_qt(on_refresh=self._apply_refresh)
        self._apply_refresh()

        self._apply_window_geometry()

        # ── 主布局：侧栏 | 分隔条 | 右侧 ──
        central = QWidget()
        main_layout = QVBoxLayout(central)
        main_layout.setContentsMargins(0, 0, 0, 0)
        self._splitter = QSplitter(Qt.Horizontal, central)
        main_layout.addWidget(self._splitter)
        self.setCentralWidget(central)

        app_config = load_app()
        ratio = app_config.get("sidebar_width_ratio", 0.22)
        compact = bool(app_config.get("sidebar_compact", False))
        ww = max(self.width(), 800)
        sidebar_w = 68 if compact else max(270, min(420, int(ww * ratio)))

        self.sidebar = QtSidebar(
            self._on_project_select,
            editability=None,
            on_settings_closed=self._on_settings_closed,
            on_app_close=self._on_close,
        )
        self.sidebar.setMinimumWidth(68 if compact else 260)
        self.sidebar.setMaximumWidth(68 if compact else 420)
        self.sidebar.compact_toggled.connect(self._on_sidebar_compact_toggled)

        self.content = QtContentArea(
            on_name_change=self._on_project_name_change,
            on_status_change=self._on_project_status_change,
            on_new_project=self.sidebar._new_project,
        )

        self._splitter.addWidget(self.sidebar)
        self._splitter.addWidget(self.content)
        self._splitter.setCollapsible(0, False)
        self.sidebar.set_compact(compact)
        self._splitter.setSizes([sidebar_w, max(ww - sidebar_w, 400)])
        self._splitter.setStretchFactor(0, 0)
        self._splitter.setStretchFactor(1, 1)
        self._splitter.splitterMoved.connect(self._on_splitter_moved)

        self.editability = EditabilityPolicy(
            get_current_status=self.content.get_project_status,
            current_uuid_provider=lambda: self.content.current_uuid or "",
        )
        self.content.set_editability(self.editability)
        self.sidebar._editability = self.editability
        self.sidebar.select_initial_project()

        self._setup_status_bar()
        self._bind_shortcuts()
        self._schedule_update_check()
        self._schedule_onboarding()

    # ── 状态栏：常驻保存状态 ────────────────────────────────────────────────

    def _setup_status_bar(self) -> None:
        bar = self.statusBar()
        bar.setSizeGripEnabled(False)
        bar.setStyleSheet(
            "QStatusBar { background: #f8f8fa; color: #3a3a3c;"
            " border-top: 1px solid #e5e5ea; font-size: 13px; font-weight: bold; padding: 4px 10px; }"
        )
        bar.showMessage("✓ 就绪 · 账单数据实时自动保存已开启")
        try:
            self.content._save_bridge.save_state.connect(self._on_save_state)
        except Exception as exc:
            logger.warning("[save_state] 状态栏接线失败: %s", exc)

    def _on_save_state(self, state: str, stamp: str) -> None:
        if self._closed:
            return
        from .feedback import save_state_message
        text = save_state_message(state, stamp)
        if state == "failed":
            self.statusBar().setStyleSheet(
                "QStatusBar { background: #ffeceb; color: #d70015;"
                " border-top: 1px solid #ff3b30; font-size: 13px; font-weight: bold; padding: 4px 10px; }"
            )
        elif state == "saved":
            self.statusBar().setStyleSheet(
                "QStatusBar { background: #e8f8ee; color: #1c7333;"
                " border-top: 1px solid #34c759; font-size: 13px; font-weight: bold; padding: 4px 10px; }"
            )
        else:
            self.statusBar().setStyleSheet(
                "QStatusBar { background: #ebf5ff; color: #007aff;"
                " border-top: 1px solid #007aff; font-size: 13px; padding: 4px 10px; }"
            )
        self.statusBar().showMessage(text)

    def _schedule_onboarding(self) -> None:
        def _show():
            try:
                from .onboarding import maybe_show_onboarding
                maybe_show_onboarding(self, self.content)
            except Exception as exc:
                logger.warning("[onboarding] 触发失败: %s", exc)
        QTimer.singleShot(2000, _show)

    # ── 主题 / 字体刷新 ─────────────────────────────────────────────────────

    def _apply_refresh(self) -> None:
        app = QApplication.instance()
        if app is not None:
            app.setStyleSheet(build_qss())
        self.setFont(font_manager.get("body"))
        if hasattr(self, "sidebar") and hasattr(self, "content"):
            self.sidebar._apply_fonts()
            self.content._apply_fonts()

    # ── 窗口几何（JSON 持久化，复用 Tk 版逻辑）─────────────────────────────

    def _apply_window_geometry(self) -> None:
        cfg = load_app()
        saved = cfg.get("window_sizes", {}).get(self.WINDOW_KEY)
        if saved and isinstance(saved, list) and len(saved) == 2:
            w, h = int(saved[0]), int(saved[1])
            sw = self.screen().availableGeometry()
            if w > 200 and h > 200:
                w = min(w, sw.width())
                h = min(h, sw.height())
                x = max(0, (sw.width() - w) // 2)
                y = max(0, (sw.height() - h) // 2)
                self.resize(w, h)
                self.move(x, y)
                return
        self.showMaximized()

    def _save_window_geometry(self) -> None:
        self._save_after_id = None
        w, h = self.width(), self.height()
        if w < 200 or h < 200:
            return
        cfg = load_app()
        sizes = cfg.setdefault("window_sizes", {})
        if sizes.get(self.WINDOW_KEY) != [w, h]:
            sizes[self.WINDOW_KEY] = [w, h]
            logger.debug("[win_geom] saving: %dx%d", w, h)
            try:
                save_app(cfg)
            except Exception as e:
                logger.warning("[win_geom] 保存失败: %s", e)

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        if self._closed:
            return
        if self._save_after_id is not None:
            self._save_after_id.stop()
        self._save_after_id = QTimer(self)
        self._save_after_id.setSingleShot(True)
        self._save_after_id.setInterval(200)
        self._save_after_id.timeout.connect(self._save_window_geometry)
        self._save_after_id.start()

    # ── 侧栏比例持久化 ──────────────────────────────────────────────────────

    def _on_splitter_moved(self, _pos: int, _index: int) -> None:
        if getattr(self.sidebar, "_compact", False):
            return
        try:
            win_w = self.width()
            sidebar_w = self.sidebar.width()
            ratio = round(sidebar_w / max(win_w, 1), 6)
            cfg = load_app()
            old = cfg.get("sidebar_width_ratio", 0)
            if abs(old - ratio) > 1e-6:
                cfg["sidebar_width_ratio"] = ratio
                save_app(cfg)
                logger.debug("[sidebar] saved: %.6f", ratio)
        except Exception as e:
            logger.error("[sidebar] save failed: %s", e, exc_info=True)

    def _on_sidebar_compact_toggled(self, compact: bool) -> None:
        cfg = load_app()
        if compact:
            self.sidebar.setMinimumWidth(68)
            self.sidebar.setMaximumWidth(68)
            sizes = self._splitter.sizes()
            if sizes and sizes[0] > 80:
                cfg["sidebar_expanded_width"] = sizes[0]
            self._splitter.setSizes([68, max(self.width() - 68, 400)])
        else:
            expanded = int(cfg.get("sidebar_expanded_width", 280))
            expanded = max(260, min(420, expanded))
            self.sidebar.setMinimumWidth(260)
            self.sidebar.setMaximumWidth(420)
            self._splitter.setSizes([expanded, max(self.width() - expanded, 400)])
        cfg["sidebar_compact"] = compact
        try:
            save_app(cfg)
        except Exception as exc:
            logger.warning("[sidebar] compact state save failed: %s", exc)

    # ── 项目事件回调 ────────────────────────────────────────────────────────

    def _on_project_select(self, uuid) -> None:
        self.content.load_project(uuid)

    def _on_project_name_change(self, uuid: str, new_name: str) -> None:
        try:
            self.sidebar.update_item_name(uuid, new_name)
        except Exception:
            pass

    def _on_project_status_change(self, uuid: str, new_status) -> None:
        try:
            self.sidebar.update_item_status(uuid, new_status)
        except Exception:
            pass

    def _on_settings_closed(self) -> None:
        get_voice().stop()
        self.content.refresh_app_settings()

    # ── 快捷键 ──────────────────────────────────────────────────────────────

    def _bind_shortcuts(self) -> None:
        sm.init(self)
        sm.bind_qt(self)

    # ── 更新检查（P2：仅日志；P4 接 UpdateDialog）──────────────────────────

    def _schedule_update_check(self) -> None:
        if self._closed or self._update_check_running:
            return
        if self._update_check_after_id is not None:
            return
        self._update_check_after_id = QTimer(self)
        self._update_check_after_id.setSingleShot(True)
        self._update_check_after_id.setInterval(3000)
        self._update_check_after_id.timeout.connect(self._do_update_check)
        self._update_check_after_id.start()

    def _do_update_check(self) -> None:
        self._update_check_after_id = None
        if self._closed or self._update_check_running:
            return
        self._update_check_running = True
        try:
            checker = UpdateChecker()
            self._update_checker = checker
            checker.run_async()

            def _poll():
                self._update_poll_after_id = None
                if self._closed or checker is not self._update_checker:
                    return
                if checker.is_done:
                    self._update_check_running = False
                    self._update_checker = None
                    if checker.result:
                        logger.info("[updater] 发现新版本: %s", checker.result.latest_version)
                else:
                    self._update_poll_after_id = QTimer(self)
                    self._update_poll_after_id.setSingleShot(True)
                    self._update_poll_after_id.setInterval(500)
                    self._update_poll_after_id.timeout.connect(_poll)
                    self._update_poll_after_id.start()

            self._update_poll_after_id = QTimer(self)
            self._update_poll_after_id.setSingleShot(True)
            self._update_poll_after_id.setInterval(500)
            self._update_poll_after_id.timeout.connect(_poll)
            self._update_poll_after_id.start()
        except Exception as e:
            self._update_check_running = False
            self._update_checker = None
            logger.warning("启动时检查更新失败: %s", e)

    # ── 关闭 ────────────────────────────────────────────────────────────────

    def _on_close(self) -> None:
        if self._closed:
            return
        self._closed = True
        for timer_attr in ("_save_after_id", "_update_check_after_id", "_update_poll_after_id"):
            timer = getattr(self, timer_attr, None)
            if timer is not None:
                try:
                    timer.stop()
                except Exception:
                    pass
                setattr(self, timer_attr, None)
        self._update_check_running = False
        self._update_checker = None

        content = getattr(self, "content", None)
        if content is not None:
            try:
                content.flush_project_save()
            except Exception as exc:
                logger.warning("关闭前刷新项目保存队列失败: %s", exc)

        try:
            self._save_window_geometry()
        except Exception as exc:
            logger.warning("关闭时保存窗口尺寸失败: %s", exc)

        try:
            sm._unbind_qt()
        except Exception as exc:
            logger.debug("关闭快捷键清理异常: %s", exc)

        try:
            from ...voice import VoiceEngine
            if VoiceEngine._instance is not None:
                VoiceEngine._instance.shutdown()
        except Exception as exc:
            logger.debug("关闭语音引擎时忽略异常: %s", exc)

    def closeEvent(self, event) -> None:
        self._on_close()
        event.accept()
