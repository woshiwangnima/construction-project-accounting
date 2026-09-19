"""Qt 应用启动（替代 Tk main.py 路径）。

临时入口 qt_main.py 调用本模块 main()；P5 合并后由 main.py 直接走 Qt。
"""
import sys
import traceback

from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication, QMessageBox

from ...logger import logger, setup_logger
from ...paths import get_resource_root, migrate_legacy_data
from ...single_instance import SingleInstanceLock
from ...versioning import migrate_all_known_files
from .main_window import MainWindow


def _apply_app_icon(app: QApplication) -> None:
    """设置应用图标（窗口标题栏/任务栏），并固定 Windows AppUserModelID。"""
    icon_file = get_resource_root() / "assets" / "icon.ico"
    if icon_file.is_file():
        app.setWindowIcon(QIcon(str(icon_file)))
    if sys.platform == "win32":
        try:
            import ctypes

            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(
                "ConstructionAccounting"
            )
        except Exception:
            logger.warning("Failed to set AppUserModelID", exc_info=True)


def _align_fluent_theme() -> None:
    """把 qfluentwidgets 局部组件的主题对齐到本应用的设计体系。

    SwitchButton / InfoBar / MessageBox / TeachingTip 这些零散组件由
    qfluentwidgets 自绘，用的是它自己的主题色（默认青色 #009faa）和明暗设置，
    不跟随 ``theme.py``。不显式对齐的话，界面里会出现第二种蓝色；
    系统处于深色模式时，这些弹窗还会变成深色，与全浅色的主界面割裂。
    """
    try:
        from qfluentwidgets import Theme, setTheme, setThemeColor
    except Exception:
        logger.debug("qfluentwidgets 不可用，跳过主题对齐", exc_info=True)
        return
    from ..theme import ACCENT
    try:
        setTheme(Theme.LIGHT)
        setThemeColor(ACCENT)
        logger.debug("qfluentwidgets 主题已对齐到 %s", ACCENT)
    except Exception:
        logger.warning("qfluentwidgets 主题对齐失败", exc_info=True)


def main() -> None:
    setup_logger()
    instance_lock = SingleInstanceLock()
    if not instance_lock.acquire():
        app = QApplication.instance() or QApplication(sys.argv)
        QMessageBox.warning(None, "数据正在使用", "桌面程序或写入命令正在使用数据，请稍后重试。")
        return
    app = QApplication(sys.argv)
    app.setApplicationName("施工项目记账程序")
    _apply_app_icon(app)
    _align_fluent_theme()
    try:
        copied, failures = migrate_legacy_data()
        if copied:
            logger.info("Legacy data migration copied %d files", copied)
        for failure in failures:
            logger.warning("Legacy data migration failed: %s", failure)
        migrate_all_known_files()
        window = MainWindow()
        window.show()
        app.exec()
    except Exception:
        logger.critical("程序启动失败:\n%s", traceback.format_exc())
        raise
    finally:
        try:
            instance_lock.release()
        except Exception:
            pass


if __name__ == "__main__":
    main()
