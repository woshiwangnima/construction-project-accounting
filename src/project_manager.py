import copy
import json
import os
import re
import shutil
import uuid as uuid_module
from datetime import datetime
from pathlib import Path

from .logger import logger
from .utils import atomic_write_json
from .project import Project
from .project_status import ProjectStatus
from .category import Category
from .trade_item import TradeItem
from .bill import Bill
from .billing import Billing, write_billing
from .backup_policy import next_sequence_backup_path, rotate_sequence_backups, should_backup
from .trade_item_id import (
    generate_category_id,
    generate_trade_item_id,
    compute_bill_id,
)
from .project_uuid import (
    generate_project_uuid,
    project_file_path,
    backup_file_path,
    extract_uuid_from_filename,
    is_valid_project_filename,
    get_projects_dir,
    get_backups_dir,
    PROJECTS_DIR,
    BACKUPS_DIR,
)

_BASE_DIR = os.path.dirname(os.path.dirname(__file__))
CONFIG_DIR = os.environ.get("CPA_CONFIG_DIR", os.path.join(_BASE_DIR, "config"))


def _validate_uuid(uuid_str: str) -> str:
    if not uuid_str:
        raise ValueError(f"Invalid project uuid: {uuid_str}")
    if re.match(r'^project_\d{4,8}_\d{3}$', uuid_str):
        return uuid_str
    m = re.match(r'^p_([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})$', uuid_str)
    if m:
        return m.group(1)
    try:
        parsed = uuid_module.UUID(uuid_str)
        return str(parsed)
    except (TypeError, ValueError, AttributeError):
        pass
    raise ValueError(f"Invalid project uuid: {uuid_str}")


def _safe_path(base_dir: str, filename: str) -> str:
    if base_dir == PROJECTS_DIR:
        base_dir = get_projects_dir()
    elif base_dir == BACKUPS_DIR:
        base_dir = get_backups_dir()
    full = os.path.normpath(os.path.join(base_dir, filename))
    if not full.startswith(os.path.normpath(base_dir)):
        raise ValueError(f"Path traversal detected: {filename}")
    return full


def _load_default_items() -> list[dict]:
    """从 app_config.json::default_trade_items 加载默认工作项目。

    返回 dict 列表（不是 TradeItem dataclass），调用方（create_project）负责
    关联 category_id 并转 dataclass。
    """
    path = _safe_path(CONFIG_DIR, "app_config.json")
    with open(path, encoding="utf-8") as f:
        cfg = json.load(f)
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
    path = _safe_path(CONFIG_DIR, "app_config.json")
    with open(path, encoding="utf-8") as f:
        cfg = json.load(f)
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
) -> Project:
    if created_at is None:
        created_at = datetime.now().strftime("%Y-%m-%d")
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    project_uuid = generate_project_uuid()
    file_path = project_file_path(project_uuid)

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
        description="",
        project_date_type=project_date_type,
        project_date_start=project_date_start,
        project_date_end=project_date_end,
        category_order=category_order,
        trade_items=trade_items,
        bills=[],
        bill_column_widths={},
    )
    atomic_write_json(str(file_path), project.to_dict())
    _invalidate_list_cache()
    return project


_list_cache: list[Project] | None = None
_list_cache_dir_mtime: float | None = None


def _invalidate_list_cache():
    global _list_cache, _list_cache_dir_mtime
    _list_cache = None
    _list_cache_dir_mtime = None


def list_projects() -> list[Project]:
    global _list_cache, _list_cache_dir_mtime

    projects_dir = get_projects_dir()
    if not os.path.isdir(projects_dir):
        return []

    try:
        current_mtime = os.path.getmtime(projects_dir)
    except OSError:
        return []

    if _list_cache is not None and _list_cache_dir_mtime == current_mtime:
        return _list_cache

    projects: list[Project] = []
    for f in os.listdir(projects_dir):
        u = extract_uuid_from_filename(f)
        if not u:
            continue
        file_path = os.path.join(projects_dir, f)
        try:
            with open(file_path, encoding="utf-8") as fh:
                data = json.load(fh)
            data.setdefault("project_uuid", u)
            project = Project.from_dict(data)
            projects.append(project)
        except (json.JSONDecodeError, OSError) as e:
            logger.warning("Failed to load project %s: %s", f, e)
    projects.sort(key=lambda p: p.last_modified, reverse=True)

    _list_cache = projects
    _list_cache_dir_mtime = current_mtime
    return _list_cache


def delete_project(uuid: str) -> bool:
    uuid = _validate_uuid(uuid)
    file_path = project_file_path(uuid)
    if not file_path.is_file():
        old_path = Path(_safe_path(PROJECTS_DIR, f"{uuid}.json"))
        if old_path.is_file():
            file_path = old_path
        else:
            return False
    _backup_project(uuid)
    os.remove(str(file_path))
    _invalidate_list_cache()
    return True


def get_project(uuid: str) -> Project | None:
    uuid = _validate_uuid(uuid)
    file_path = project_file_path(uuid)
    if not file_path.is_file():
        old_path = Path(_safe_path(PROJECTS_DIR, f"{uuid}.json"))
        if old_path.is_file():
            file_path = old_path
        else:
            file_path = _find_project_file(uuid)
            if file_path is None:
                return None
    with open(file_path, encoding="utf-8") as f:
        data = json.load(f)
    data.setdefault("project_uuid", uuid)
    return Project.from_dict(data)


def _find_project_file(uuid: str) -> Path | None:
    projects_dir = get_projects_dir()
    if not os.path.isdir(projects_dir):
        return None
    for name in os.listdir(projects_dir):
        if not name.endswith(".json"):
            continue
        path = Path(_safe_path(PROJECTS_DIR, name))
        if path.stem == uuid:
            return path
        try:
            with open(path, encoding="utf-8") as f:
                data = json.load(f)
        except (OSError, json.JSONDecodeError):
            continue
        if data.get("project_uuid") == uuid:
            return path
    return None


def _get_backup_count() -> int:
    path = os.path.join(CONFIG_DIR, "app_config.json")
    try:
        with open(path, encoding="utf-8") as f:
            cfg = json.load(f)
        return max(1, int(cfg.get("backup_count", 10)))
    except Exception:
        return 10


def _backup_project(uuid: str, force: bool = False, next_project: dict | None = None):
    """备份项目到 backups/。"""
    uuid = _validate_uuid(uuid)
    src = project_file_path(uuid)
    if not src.is_file():
        old_path = Path(_safe_path(PROJECTS_DIR, f"{uuid}.json"))
        if old_path.is_file():
            src = old_path
        else:
            return
    backups_dir = get_backups_dir()
    os.makedirs(backups_dir, exist_ok=True)

    if not force and next_project is not None:
        try:
            with open(src, encoding="utf-8") as f:
                current = json.load(f)
        except (OSError, json.JSONDecodeError):
            current = {}
        if not should_backup(current, next_project):
            return
    elif not force:
        return

    dst = next_sequence_backup_path(src, Path(backups_dir))
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(str(src), str(dst))
    n = _get_backup_count()
    rotate_sequence_backups(src, Path(backups_dir), n)


def update_project(uuid: str, project: Project) -> None:
    """整体更新项目。Project 已是 dataclass，序列化由 to_dict() 完成。"""
    uuid = _validate_uuid(uuid)
    if not isinstance(project, Project):
        data = dict(project)
        data.setdefault("project_uuid", uuid)
        project = Project.from_dict(data)
    project.last_modified = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    next_data = project.to_dict()
    file_path = project_file_path(uuid)
    if not file_path.is_file():
        existing = _find_project_file(uuid)
        if existing is not None:
            file_path = existing
    _backup_project(uuid, next_project=next_data)
    atomic_write_json(str(file_path), next_data)
    _invalidate_list_cache()


def normalize_project(data: dict) -> dict:
    """兼容旧测试/调用方：归一化为当前 Project JSON dict。"""
    return Project.from_dict(data or {}).to_dict()


def save_project_as(project: Project, output_path: str) -> None:
    """将 Project dataclass 落盘到指定路径（用于导出）。"""
    atomic_write_json(output_path, project.to_dict())


def export_project(uuid: str, output_path: str) -> bool:
    project = get_project(uuid)
    if not project:
        return False
    save_project_as(project, output_path)
    return True


def import_project(input_path: str) -> Project | None:
    with open(input_path, encoding="utf-8") as f:
        data = json.load(f)
    if "name" not in data:
        raise ValueError("无效的项目文件：缺少 name 字段")
    return create_project(
        name=data.get("name", "导入项目"),
        status=data.get("status", ProjectStatus.EDITING),
        created_at=data.get("created_at"),
        project_date_type=data.get("project_date_type", "无时间"),
        project_date_start=data.get("project_date_start", ""),
        project_date_end=data.get("project_date_end", ""),
    )
