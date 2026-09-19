"""Project file storage, migration, recovery, and isolated listing snapshots.

The public facade in project_manager owns project creation and import semantics.
This module owns disk access and never imports that facade.
"""

import copy
import json
import os
import re
import threading
import uuid as uuid_module
from datetime import datetime
from pathlib import Path

from .backup_policy import list_backup_paths
from .logger import logger
from .project import Project
from .project_backups import create_backup
from .project_uuid import extract_uuid_from_filename, get_backups_dir, get_projects_dir
from .utils import atomic_write_json
from .versioning import MigrationError, migrate_json_document

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


_list_cache: list[Project] | None = None
_list_cache_key: tuple | None = None
_list_cache_generation = 0
_list_cache_lock = threading.Lock()


def _invalidate_list_cache() -> None:
    global _list_cache, _list_cache_key, _list_cache_generation
    with _list_cache_lock:
        _list_cache = None
        _list_cache_key = None
        _list_cache_generation += 1


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
        with _project_write_lock(project_uuid):
            # A save may have repaired the file while recovery waited for the
            # write lock. Parse directly here: calling the recovery loader again
            # would recursively acquire this non-reentrant lock.
            try:
                with open(file_path, encoding="utf-8") as fh:
                    current = json.load(fh)
            except (OSError, UnicodeError, json.JSONDecodeError):
                current = None
            if isinstance(current, dict):
                try:
                    return _parse_project_data(current, project_uuid)
                except ValueError:
                    pass
                # Preserve a readable pin state even in an invalid document.
                if "is_pinned" in current:
                    recovered.is_pinned = bool(current.get("is_pinned", False))
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


def _listing_snapshot(projects_dir: str) -> tuple[tuple, list[tuple[Path, str]]]:
    """Include the directory and file metadata so switching roots cannot hit stale cache."""
    root = Path(projects_dir).expanduser().resolve()
    entries: list[tuple[Path, str]] = []
    signature = []
    for name in os.listdir(root):
        project_uuid = extract_uuid_from_filename(name)
        if not project_uuid:
            continue
        try:
            path = Path(_safe_path(str(root), name))
            stat = path.stat()
        except (ValueError, OSError) as exc:
            logger.warning("Ignoring unreadable project %s: %s", name, exc)
            continue
        entries.append((path, project_uuid))
        signature.append((name, stat.st_mtime_ns, stat.st_size))
    return (str(root), tuple(sorted(signature))), entries


def list_projects() -> list[Project]:
    global _list_cache, _list_cache_key
    try:
        key, entries = _listing_snapshot(get_projects_dir())
    except OSError:
        return []

    with _list_cache_lock:
        generation = _list_cache_generation
        if _list_cache is not None and _list_cache_key == key:
            return copy.deepcopy(_list_cache)

    projects: list[Project] = []
    for path, project_uuid in entries:
        try:
            projects.append(_load_project_from_file(path, project_uuid))
        except (ValueError, OSError) as exc:
            logger.warning("Failed to load project %s: %s", path.name, exc)
    projects.sort(key=lambda project: (not project.is_pinned, project.last_modified), reverse=True)

    with _list_cache_lock:
        # A concurrent save or recovery invalidates this load's snapshot.
        if generation == _list_cache_generation:
            _list_cache = copy.deepcopy(projects)
            _list_cache_key = key
    return projects


def delete_project(uuid: str, *, backup_count: int, backup_max_bytes: int) -> bool:
    uuid = _validate_uuid(uuid)
    file_path = _project_path(uuid)
    if not file_path.is_file():
        old_path = Path(_safe_path(get_projects_dir(), f"{uuid}.json"))
        if old_path.is_file():
            file_path = old_path
        else:
            return False
    with _project_write_lock(uuid):
        _backup_project(uuid, force=True, count=backup_count, max_bytes=backup_max_bytes)
        os.remove(str(file_path))
    _invalidate_list_cache()
    return True


def get_project(uuid: str) -> Project | None:
    uuid = _validate_uuid(uuid)
    file_path = _project_path(uuid)
    if not file_path.is_file():
        old_path = Path(_safe_path(get_projects_dir(), f"{uuid}.json"))
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
        old_path = Path(_safe_path(get_projects_dir(), f"{uuid}.json"))
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


def _backup_project(
    uuid: str,
    force: bool = False,
    next_project: dict | None = None,
    *,
    count: int,
    max_bytes: int,
) -> None:
    """备份项目到 backups/。"""
    uuid = _validate_uuid(uuid)
    src = _project_path(uuid)
    if not src.is_file():
        old_path = Path(_safe_path(get_projects_dir(), f"{uuid}.json"))
        if old_path.is_file():
            src = old_path
        else:
            existing = _find_project_file(uuid)
            if existing is not None:
                src = existing
            else:
                return
    create_backup(
        src, Path(get_backups_dir()), count=count, max_bytes=max_bytes,
        force=force, next_project=next_project,
    )


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


def write_new_project(project: Project) -> None:
    """Persist a newly assigned UUID without creating a previous-version backup."""
    project_uuid = _validate_uuid(project.project_uuid)
    with _project_write_lock(project_uuid):
        atomic_write_json(str(_project_path(project_uuid)), project.to_dict())
    _invalidate_list_cache()


def save_project_data(
    uuid: str, next_data: dict, *, backup_count: int, backup_max_bytes: int,
) -> None:
    """Merge disk-owned pin state and back up the previous document atomically."""
    uuid = _validate_uuid(uuid)
    file_path = _project_path(uuid)
    if not file_path.is_file():
        existing = _find_project_file(uuid)
        if existing is not None:
            file_path = existing
    with _project_write_lock(uuid):
        pinned = _read_current_pin_state(file_path)
        if pinned is not None:
            next_data["is_pinned"] = pinned
        _backup_project(
            uuid, next_project=next_data, count=backup_count, max_bytes=backup_max_bytes,
        )
        atomic_write_json(str(file_path), next_data)
    _invalidate_list_cache()


def save_project_as(project: Project, output_path: str) -> None:
    """将 Project dataclass 落盘到指定路径（用于导出）。"""
    atomic_write_json(output_path, project.to_dict())
