"""项目导入 / 导出对话框（Qt）。

封装 QFileDialog（JSON 文件）+ src/project_manager.import_project / export_project；
成功后回调 on_done()。
"""
from PySide6.QtWidgets import QFileDialog, QMessageBox

from ....logger import logger
from ....project_manager import export_project, get_project, import_project


def import_project_dialog(parent, on_done=None) -> None:
    """选择 JSON 文件导入为全新项目。成功回调 on_done()。"""
    path, _ = QFileDialog.getOpenFileName(
        parent,
        "导入项目",
        "",
        "项目文件 (*.json);;所有文件 (*.*)",
    )
    if not path:
        return
    try:
        project = import_project(path)
    except (ValueError, OSError) as exc:
        logger.warning("[import] 导入失败: %s", exc)
        QMessageBox.critical(parent, "导入失败", str(exc))
        return
    name = project.get("name", "") if project is not None else ""
    QMessageBox.information(parent, "导入成功", f"项目「{name}」已导入。")
    if on_done is not None:
        try:
            on_done()
        except Exception as exc:
            logger.debug("[import] on_done callback raised: %s", exc)


def export_project_dialog(parent, uuid: str, on_done=None) -> None:
    """把项目导出为 JSON 文件。成功回调 on_done()。"""
    project = get_project(uuid)
    if project is None:
        QMessageBox.warning(parent, "导出项目", "项目不存在或无法读取。")
        return
    default_name = f"{project.get('name', '项目')}.json"
    path, _ = QFileDialog.getSaveFileName(
        parent,
        "导出项目",
        default_name,
        "项目文件 (*.json);;所有文件 (*.*)",
    )
    if not path:
        return
    if not path.lower().endswith(".json"):
        path += ".json"
    try:
        ok = export_project(uuid, path)
    except (ValueError, OSError) as exc:
        logger.warning("[export] 导出失败: %s", exc)
        QMessageBox.critical(parent, "导出失败", str(exc))
        return
    if not ok:
        QMessageBox.warning(parent, "导出项目", "项目不存在或无法读取。")
        return
    QMessageBox.information(parent, "导出成功", f"项目已导出到：\n{path}")
    if on_done is not None:
        try:
            on_done()
        except Exception as exc:
            logger.debug("[export] on_done callback raised: %s", exc)
