import copy
import json
import os
import re
import shutil
import tempfile
import threading
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
from .backup_policy import (
    next_sequence_backup_path,
    should_backup,
    rotate_sequence_backups,
    list_backup_paths,
)
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
)
from .versioning import CURRENT_SCHEMA_VERSION, MigrationError, migrate_json_document
from .config_loader import load_app

_BASE_DIR = os.path.dirname(os.path.dirname(__file__))
CONFIG_DIR = os.environ.get("CPA_CONFIG_DIR", os.path.join(_BASE_DIR, "config"))
PROJECTS_DIR = get_projects_dir()
BACKUPS_DIR = get_backups_dir()


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
    base = Path(base_dir).expanduser().resolve()
    full = (base / str(filename)).resolve()
    try:
        full.relative_to(base)
    except ValueError:
        raise ValueError(f"Path traversal detected: {filename}")
    return str(full)


def _project_path(uuid: str) -> Path:
    """Return a project path proven to stay inside the configured directory."""
    return Path(_safe_path(get_projects_dir(), f"p_{uuid}.json"))


_project_write_locks: dict[str, threading.Lock] = {}
_project_write_locks_guard = threading.Lock()


def _project_write_lock(uuid: str) -> threading.Lock:
    """串行化同一项目的一切写操作（GUI 后台保存、对话框、置顶切换）。

    后台保存 worker 与主线程 toggle_pin/对话框保存并发时，靠这把锁保证
    磁盘上的读-改-写操作互斥，避免旧快照覆盖新数据（丢失更新）。
    """
    normalized = _validate_uuid(uuid)
    with _project_write_locks_guard:
        lock = _project_write_locks.get(normalized)
        if lock is None:
            lock = threading.Lock()
            _project_write_locks[normalized] = lock
        return lock


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
    file_path = _project_path(project_uuid)

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
    with _project_write_lock(project_uuid):
        atomic_write_json(str(file_path), project.to_dict())
    _invalidate_list_cache()
    return project


_list_cache: list[Project] | None = None
_list_cache_dir_mtime: float | None = None
_list_cache_lock = threading.Lock()


def _invalidate_list_cache():
    global _list_cache, _list_cache_dir_mtime
    with _list_cache_lock:
        _list_cache = None
        _list_cache_dir_mtime = None


def _parse_project_data(data: dict, project_uuid: str | None = None) -> Project:
    """迁移并归一化一份项目 JSON dict，结构错误时抛 ValueError。"""
    if project_uuid:
        data = dict(data)
        data.setdefault("project_uuid", project_uuid)
    try:
        migrated = migrate_json_document("project", data)
        return Project.from_dict(migrated)
    except MigrationError as exc:
        raise ValueError(f"项目文件版本不受支持：{exc}") from exc
    except (AttributeError, TypeError, ValueError, KeyError, IndexError) as exc:
        raise ValueError(f"项目数据结构无效：{exc}") from exc


def _try_recover_from_backup(file_path: Path, project_uuid: str, error: Exception) -> Project | None:
    """项目文件损坏时，尝试用最近的有效备份自动恢复。

    成功恢复：把备份内容原子写回项目文件并返回恢复的项目；
    无可用备份：返回 None，调用方维持原有"无法加载"行为。
    """
    backups_dir = get_backups_dir()
    if not os.path.isdir(backups_dir):
        return None
    candidates = list_backup_paths(project_uuid, Path(backups_dir))
    for backup_path in candidates:
        try:
            with open(backup_path, encoding="utf-8") as fh:
                data = json.load(fh)
        except (OSError, UnicodeError, json.JSONDecodeError):
            continue
        if not isinstance(data, dict):
            continue
        try:
            recovered = _parse_project_data(data, project_uuid)
        except ValueError:
            continue
        # 尽量保留损坏文件里仍可读取的置顶状态（备份通常早于置顶切换）
        try:
            with open(file_path, encoding="utf-8") as fh:
                broken = json.load(fh)
        except (OSError, UnicodeError, json.JSONDecodeError):
            broken = None
        if isinstance(broken, dict) and "is_pinned" in broken:
            recovered.is_pinned = bool(broken.get("is_pinned", False))
        with _project_write_lock(project_uuid):
            atomic_write_json(str(file_path), recovered.to_dict())
        _invalidate_list_cache()
        logger.warning(
            "项目 %s 文件损坏，已从备份 %s 自动恢复（原错误: %s）",
            project_uuid[:16], backup_path.name, error,
        )
        return recovered
    return None


def _load_project_from_file(file_path: Path, project_uuid: str | None = None) -> Project:
    """读取并归一化一个项目文件，统一处理损坏或旧格式数据。

    文件 JSON 损坏或结构无效时，尝试从最近备份自动恢复；恢复失败才抛
    ValueError（调用方降级为"无法加载"）。
    """
    try:
        with open(file_path, encoding="utf-8") as fh:
            data = json.load(fh)
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        error = ValueError(f"无法读取项目文件：{exc}")
        if project_uuid:
            recovered = _try_recover_from_backup(file_path, project_uuid, error)
            if recovered is not None:
                return recovered
        raise error
    if not isinstance(data, dict):
        error = ValueError("项目 JSON 根节点必须是对象")
        if project_uuid:
            recovered = _try_recover_from_backup(file_path, project_uuid, error)
            if recovered is not None:
                return recovered
        raise error
    try:
        return _parse_project_data(data, project_uuid)
    except ValueError as exc:
        if project_uuid:
            recovered = _try_recover_from_backup(file_path, project_uuid, exc)
            if recovered is not None:
                return recovered
        raise


def list_projects() -> list[Project]:
    global _list_cache, _list_cache_dir_mtime

    projects_dir = get_projects_dir()
    if not os.path.isdir(projects_dir):
        return []

    try:
        current_mtime = os.path.getmtime(projects_dir)
    except OSError:
        return []

    with _list_cache_lock:
        if _list_cache is not None and _list_cache_dir_mtime == current_mtime:
            return _list_cache

    projects: list[Project] = []
    for f in os.listdir(projects_dir):
        u = extract_uuid_from_filename(f)
        if not u:
            continue
        try:
            file_path = Path(_safe_path(projects_dir, f))
            project = _load_project_from_file(file_path, u)
            projects.append(project)
        except (ValueError, OSError) as e:
            logger.warning("Failed to load project %s: %s", f, e)
    projects.sort(key=lambda p: (not p.is_pinned, p.last_modified), reverse=True)

    with _list_cache_lock:
        _list_cache = projects
        _list_cache_dir_mtime = current_mtime
    return _list_cache


def delete_project(uuid: str) -> bool:
    uuid = _validate_uuid(uuid)
    file_path = _project_path(uuid)
    if not file_path.is_file():
        old_path = Path(_safe_path(PROJECTS_DIR, f"{uuid}.json"))
        if old_path.is_file():
            file_path = old_path
        else:
            return False
    with _project_write_lock(uuid):
        _backup_project(uuid, force=True)
        os.remove(str(file_path))
    _invalidate_list_cache()
    return True


def get_project(uuid: str) -> Project | None:
    uuid = _validate_uuid(uuid)
    file_path = _project_path(uuid)
    if not file_path.is_file():
        old_path = Path(_safe_path(PROJECTS_DIR, f"{uuid}.json"))
        if old_path.is_file():
            file_path = old_path
        else:
            file_path = _find_project_file(uuid)
            if file_path is None:
                return None
    try:
        return _load_project_from_file(file_path, uuid)
    except ValueError as exc:
        logger.error("Failed to load project %s: %s", uuid, exc)
        return None


def toggle_pin(uuid: str) -> bool:
    """Toggle pinned state. Does NOT trigger backup. 返回切换后的置顶状态。"""
    uuid = _validate_uuid(uuid)
    file_path = _project_path(uuid)
    if not file_path.is_file():
        old_path = Path(_safe_path(PROJECTS_DIR, f"{uuid}.json"))
        if old_path.is_file():
            file_path = old_path
        else:
            existing = _find_project_file(uuid)
            if existing is not None:
                file_path = existing
            else:
                return False
    with _project_write_lock(uuid):
        try:
            with open(file_path, encoding="utf-8") as f:
                data = json.load(f)
        except (OSError, UnicodeError, json.JSONDecodeError) as exc:
            logger.error("Failed to read project %s for pin toggle: %s", uuid, exc)
            return False
        if not isinstance(data, dict):
            logger.error("Failed to toggle pin for %s: project JSON root is not an object", uuid)
            return False
        data.setdefault("project_uuid", uuid)
        data["is_pinned"] = not data.get("is_pinned", False)
        data["last_modified"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        atomic_write_json(str(file_path), data)
    _invalidate_list_cache()
    return bool(data.get("is_pinned", False))


def _find_project_file(uuid: str) -> Path | None:
    projects_dir = get_projects_dir()
    if not os.path.isdir(projects_dir):
        return None
    for name in os.listdir(projects_dir):
        if not name.endswith(".json"):
            continue
        try:
            path = Path(_safe_path(get_projects_dir(), name))
        except ValueError:
            logger.warning("Ignoring project path outside projects directory: %s", name)
            continue
        if path.stem == uuid:
            return path
        try:
            with open(path, encoding="utf-8") as f:
                data = json.load(f)
        except (OSError, UnicodeError, json.JSONDecodeError):
            continue
        if isinstance(data, dict) and data.get("project_uuid") == uuid:
            return path
    return None


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
    """备份项目到 backups/。"""
    uuid = _validate_uuid(uuid)
    src = _project_path(uuid)
    if not src.is_file():
        old_path = Path(_safe_path(PROJECTS_DIR, f"{uuid}.json"))
        if old_path.is_file():
            src = old_path
        else:
            existing = _find_project_file(uuid)
            if existing is not None:
                src = existing
            else:
                return
    backups_dir = get_backups_dir()
    os.makedirs(backups_dir, exist_ok=True)

    if not force and next_project is not None:
        try:
            with open(src, encoding="utf-8") as f:
                current = json.load(f)
        except (OSError, UnicodeError, json.JSONDecodeError):
            current = {}
        if not should_backup(current, next_project):
            return
    elif not force:
        return

    n = _get_backup_count()
    dst = next_sequence_backup_path(src, Path(backups_dir))
    dst.parent.mkdir(parents=True, exist_ok=True)
    _copy_file_atomically(src, dst)
    rotate_sequence_backups(src, Path(backups_dir), n, _get_backup_max_bytes())


def _copy_file_atomically(source: Path, destination: Path) -> None:
    """Copy a file without exposing a partially written destination."""
    fd, temp_name = tempfile.mkstemp(
        prefix=f".{destination.name}.",
        suffix=".tmp",
        dir=str(destination.parent),
    )
    os.close(fd)
    temp_path = Path(temp_name)
    try:
        shutil.copy2(str(source), str(temp_path))
        os.replace(str(temp_path), str(destination))
        # Retention is based on backup creation time, not source mtime.
        os.utime(destination, None)
    finally:
        try:
            temp_path.unlink(missing_ok=True)
        except OSError:
            pass


def _read_current_pin_state(file_path: Path) -> bool | None:
    """读取磁盘上项目文件的当前置顶状态；文件不存在/不可读返回 None。"""
    try:
        with open(file_path, encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, UnicodeError, json.JSONDecodeError):
        return None
    if isinstance(data, dict) and "is_pinned" in data:
        return bool(data.get("is_pinned", False))
    return None


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
    next_data = project.to_dict()
    file_path = _project_path(uuid)
    if not file_path.is_file():
        existing = _find_project_file(uuid)
        if existing is not None:
            file_path = existing
    with _project_write_lock(uuid):
        # 置顶状态只由 toggle_pin 独占写入。快照可能早于置顶切换，因此
        # 保存时以磁盘上的最新值合并，避免内容保存覆盖刚切换的置顶。
        pinned = _read_current_pin_state(file_path)
        if pinned is not None:
            next_data["is_pinned"] = pinned
        _backup_project(uuid, next_project=next_data)
        atomic_write_json(str(file_path), next_data)
    _invalidate_list_cache()


def normalize_project(data: dict) -> dict:
    """兼容旧测试/调用方：归一化为当前 Project JSON dict。"""
    if not isinstance(data, dict):
        raise ValueError("项目数据必须是对象")
    try:
        migrated = migrate_json_document("project", data)
        return Project.from_dict(migrated).to_dict()
    except MigrationError as exc:
        raise ValueError(f"项目文件版本不受支持：{exc}") from exc


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

    file_path = _project_path(project.project_uuid)
    with _project_write_lock(project.project_uuid):
        atomic_write_json(str(file_path), project.to_dict())
    _invalidate_list_cache()
    return project
