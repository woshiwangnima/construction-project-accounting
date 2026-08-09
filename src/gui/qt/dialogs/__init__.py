"""Qt 业务对话框（P4）：项目/账单/工种编辑、回滚、导入导出、导出图片、设置。

相对导入约定：src.gui.qt.dialogs.X → src = 四个点（....）。
"""

from ...font_manager import font_manager

# 对话框可能在 app 启动流程之外被构造（如离屏测试），确保字体走 Qt 模式
if not font_manager.initialized:
    font_manager.init_qt()

from .edit_bill import EditBillDialog
from .edit_trade import EditTradeItemDialog
from .new_project import NewProjectDialog
from .confirm import confirm_dialog
from .rollback import RollbackDialog
from .import_export import import_project_dialog, export_project_dialog
from .export_image import ExportImageDialog

__all__ = [
    "NewProjectDialog",
    "EditBillDialog",
    "EditTradeItemDialog",
    "confirm_dialog",
    "RollbackDialog",
    "import_project_dialog",
    "export_project_dialog",
    "ExportImageDialog",
]
