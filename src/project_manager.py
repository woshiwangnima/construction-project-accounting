"""Project operations; file storage and backups live in dedicated modules.

Existing GUI, CLI, and legacy callers can continue using this facade.
"""

import copy
import json
import os
from datetime import datetime

from . import project_repository as repository
from .bill import Bill
from .billing import Billing, write_billing
from .category import Category
from .config_loader import load_app
from .project import Project
from .project_backups import copy_file_atomically as _copy_file_atomically
from .project_repository import (
    BACKUPS_DIR,
    PROJECTS_DIR,
    _find_project_file,
    _invalidate_list_cache,
    _load_project_from_file,
    _parse_project_data,
    _project_path,
    _project_write_lock,
    _read_current_pin_state,
    _safe_path,
    _try_recover_from_backup,
    _validate_uuid,
    get_project,
    list_projects,
    save_project_as,
    toggle_pin,
)
from .project_status import ProjectStatus
from .project_uuid import (
    backup_file_path,
    extract_uuid_from_filename,
    generate_project_uuid,
    get_backups_dir,
    get_projects_dir,
    is_valid_project_filename,
    project_file_path,
)
from .trade_item import TradeItem
from .trade_item_id import compute_bill_id, generate_category_id, generate_trade_item_id
from .versioning import CURRENT_SCHEMA_VERSION, MigrationError, migrate_json_document

_BASE_DIR = os.path.dirname(os.path.dirname(__file__))
CONFIG_DIR = os.environ.get("CPA_CONFIG_DIR", os.path.join(_BASE_DIR, "config"))


def _load_default_items() -> list[dict]:
    """从 app_config.json::default_trade_items 加载默认工作项目。

    返回 dict 列表（不是 TradeItem dataclass），调用方（create_project）负责
    关联 category_id 并转 dataclass。
    """
    cfg = load_app()
    items = copy.deepcopy(cfg.get("default_trade_items", []))
    seen_ids: set[str] = set()
    for it in items:
        write_billing(it, Billing.from_dict(it))
        if not it.get("id"):
            it["id"] = generate_trade_item_id()
        base_id = it["id"]
        suffix = 2
        while it["id"] in seen_ids:
            it["id"] = f"{base_id}-{suffix}"
            suffix += 1
        seen_ids.add(it["id"])
    return items


def _load_default_categories() -> list[Category]:
    cfg = load_app()
    categories = []
    seen: set[str] = set()
    for c in cfg.get("default_categories", []) or []:
        cat = Category.from_dict(c)
        if cat.id and cat.id not in seen:
            categories.append(cat)
            seen.add(cat.id)
    return categories


def _ensure_bill_id(bill: Bill) -> None:
    if not bill.id:
        bill.id = compute_bill_id(bill.trade_item_id, bill.content, bill.record_time)


def ensure_bill_id(bill) -> None:
    if isinstance(bill, Bill):
        _ensure_bill_id(bill)
        return
    if not bill.get("id"):
        bill["id"] = compute_bill_id(
            bill.get("trade_item_id", ""),
            bill.get("content", ""),
            bill.get("record_time", ""),
        )


def create_project(
    name: str,
    status: str | ProjectStatus = ProjectStatus.EDITING,
    created_at: str | None = None,
    project_date_type: str = "无时间",
    project_date_start: str = "",
    project_date_end: str = "",
    description: str = "",
) -> Project:
    if created_at is None:
        created_at = datetime.now().strftime("%Y-%m-%d")
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    project_uuid = generate_project_uuid()

    default_items = _load_default_items()

    category_order = _load_default_categories()
    cat_id_by_name: dict[str, str] = {c.name: c.id for c in category_order}
    cat_name_by_id: dict[str, str] = {c.id: c.name for c in category_order}
    for ti in default_items:
        cat = ti.get("category", "")
        category_id = ti.get("category_id", "")
        if category_id and category_id not in cat_name_by_id:
            category_order.append(Category(id=category_id, name=cat or category_id))
            cat_name_by_id[category_id] = cat or category_id
            if cat:
                cat_id_by_name[cat] = category_id
        elif cat and cat not in cat_id_by_name:
            cat_id = generate_category_id()
            category_order.append(Category(id=cat_id, name=cat))
            cat_id_by_name[cat] = cat_id
            cat_name_by_id[cat_id] = cat
    trade_items = [
        TradeItem(
            id=ti["id"],
            category_id=ti.get("category_id") or cat_id_by_name.get(ti.get("category", ""), ""),
            name=ti["name"],
            has_unit=ti["has_unit"],
            unit_price=ti["unit_price"],
            unit=ti["unit"],
            category=ti.get("category") or cat_name_by_id.get(ti.get("category_id", ""), ""),
        )
        for ti in default_items
    ]

    status_value = status.value if isinstance(status, ProjectStatus) else ProjectStatus.from_value(status).value

    project = Project(
        project_uuid=project_uuid,
        name=name,
        status=status_value,
        created_at=created_at,
        last_modified=now_str,
        description=description,
        project_date_type=project_date_type,
        project_date_start=project_date_start,
        project_date_end=project_date_end,
        category_order=category_order,
        trade_items=trade_items,
        bills=[],
        bill_column_widths={},
    )
    repository.write_new_project(project)
    return project


def _get_backup_count() -> int:
    try:
        return max(1, int(load_app().get("backup_count", 10)))
    except Exception:
        return 10


def _get_backup_max_bytes() -> int:
    """备份保留的字节上限；0 表示不限制。"""
    try:
        return max(0, int(load_app().get("backup_max_bytes", 0)))
    except Exception:
        return 0


def _backup_project(uuid: str, force: bool = False, next_project: dict | None = None):
    """Compatibility entry point used by rollback and backup configuration tests."""
    repository._backup_project(
        uuid, force=force, next_project=next_project,
        count=_get_backup_count(), max_bytes=_get_backup_max_bytes(),
    )


def delete_project(uuid: str) -> bool:
    return repository.delete_project(
        uuid, backup_count=_get_backup_count(), backup_max_bytes=_get_backup_max_bytes(),
    )


def update_project(uuid: str, project: Project) -> None:
    """整体更新项目。Project 已是 dataclass，序列化由 to_dict() 完成。"""
    uuid = _validate_uuid(uuid)
    if not isinstance(project, Project):
        data = dict(project)
        data.setdefault("project_uuid", uuid)
        project = Project.from_dict(data)
    # The caller's UUID identifies the file being updated; keep the payload
    # consistent with it even when a stale in-memory object is supplied.
    project.project_uuid = uuid
    project.last_modified = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    repository.save_project_data(
        uuid, project.to_dict(),
        backup_count=_get_backup_count(), backup_max_bytes=_get_backup_max_bytes(),
    )


def normalize_project(data: dict) -> dict:
    """兼容旧测试/调用方：归一化为当前 Project JSON dict。"""
    if not isinstance(data, dict):
        raise ValueError("项目数据必须是对象")
    try:
        migrated = migrate_json_document("project", data)
        return Project.from_dict(migrated).to_dict()
    except MigrationError as exc:
        raise ValueError(f"项目文件版本不受支持：{exc}") from exc


def export_project(uuid: str, output_path: str) -> bool:
    project = get_project(uuid)
    if not project:
        return False
    save_project_as(project, output_path)
    return True


def import_project(input_path: str) -> Project | None:
    """导入完整项目数据并生成新的项目 UUID。

    导入不能调用 ``create_project`` 后再拼字段：那会先注入默认工种，
    也容易遗漏项目描述、账单列宽和视图状态。这里直接把导出的 JSON
    归一化为 Project，再以新 UUID 写入目标目录。
    """
    try:
        with open(input_path, encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"无法读取项目文件：{exc}") from exc

    if not isinstance(data, dict):
        raise ValueError("无效的项目文件：JSON 根节点必须是对象")

    name = str(data.get("name", "")).strip()
    if not name:
        raise ValueError("无效的项目文件：缺少有效的 name 字段")

    try:
        migrated = migrate_json_document("project", data)
        project = Project.from_dict(migrated)
    except MigrationError as exc:
        raise ValueError(f"项目文件版本不受支持：{exc}") from exc
    except (AttributeError, TypeError, ValueError, KeyError, IndexError) as exc:
        raise ValueError(f"无效的项目文件：数据结构错误（{exc}）") from exc

    # 项目导入始终创建副本，避免覆盖原项目或产生同 UUID 文件。
    project.project_uuid = generate_project_uuid()
    project.name = name
    if not project.created_at:
        project.created_at = datetime.now().strftime("%Y-%m-%d")
    project.last_modified = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    project.schema_version = CURRENT_SCHEMA_VERSION

    repository.write_new_project(project)
    return project
