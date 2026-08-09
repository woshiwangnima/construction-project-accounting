"""PySide6 (Qt) GUI 层（迁移中；P5 完成后移入 src.gui 根）。

相对导入约定：src.gui.qt.X → src = 三个点（...）。
"""
from .main_window import MainWindow

__all__ = ["MainWindow"]
