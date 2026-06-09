"""UUID 工具模块：生成、派生、路径、文件名校验。"""

import os
import re
import uuid as uuid_module
from pathlib import Path
from typing import Optional

from .backup_policy import list_backup_paths

_BASE_DIR = os.path.dirname(os.path.dirname(__file__))
PROJECTS_DIR = os.environ.get("CPA_PROJECTS_DIR", os.path.join(_BASE_DIR, "projects"))
BACKUPS_DIR = os.environ.get("CPA_BACKUPS_DIR", os.path.join(_BASE_DIR, "backups"))


def get_projects_dir() -> str:
    return os.environ.get("CPA_PROJECTS_DIR", PROJECTS_DIR)


def get_backups_dir() -> str:
    return os.environ.get("CPA_BACKUPS_DIR", BACKUPS_DIR)

_UUID_PATTERN = r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}"
_PROJECT_FILE_RE = re.compile(rf"^p_({_UUID_PATTERN})(_\d+_\d+)?\.json$")

_NAMESPACE = uuid_module.UUID("6ba7b810-9dad-11d1-80b4-00c04fd430c8")  # NAMESPACE_DNS
_UUID_PREFIX = "construction-project-accounting"


def derive_uuid(ref: str) -> str:
    """从旧 ref 派生幂等 UUID5。

    同一 ref 永远返回相同 uuid。用于迁移脚本走文件重命名。
    """
    return str(uuid_module.uuid5(_NAMESPACE, f"{_UUID_PREFIX}/{ref}"))


def generate_project_uuid() -> str:
    """生成新随机 UUID4。用于 create_project。"""
    return str(uuid_module.uuid4())


def _project_filename(uuid_str: str) -> str:
    return f"p_{uuid_str}.json"


def _backup_filename(uuid_str: str, ts: str) -> str:
    return f"p_{uuid_str}_{ts}.json"


def project_file_path(uuid_str: str) -> Path:
    return Path(get_projects_dir()) / _project_filename(uuid_str)


def backup_file_path(uuid_str: str, ts: str) -> Path:
    return Path(get_backups_dir()) / _backup_filename(uuid_str, ts)


def extract_uuid_from_filename(name: str) -> Optional[str]:
    """从 `p_{uuid}.json` 或 `p_{uuid}_{ts}.json` 提取 uuid。

    非 p_ 开头/格式不符 → None。
    """
    m = _PROJECT_FILE_RE.match(name)
    if m:
        return m.group(1)
    return None


def is_valid_project_filename(name: str) -> bool:
    """p_{uuid}.json 格式校验。替代旧 _PROJECT_REF_RE。"""
    return _PROJECT_FILE_RE.match(name) is not None


def list_all_project_files() -> list[str]:
    """返回 projects/ 下所有 p_{uuid}.json 的 uuid 列表。"""
    projects_dir = get_projects_dir()
    if not os.path.isdir(projects_dir):
        return []
    result = []
    for f in os.listdir(projects_dir):
        u = extract_uuid_from_filename(f)
        if u:
            result.append(u)
    return result


def list_all_backup_files(uuid_str: str) -> list[Path]:
    """返回 backups/ 下所有 p_{uuid}_{ts}.json 备份的 Path，按时间倒序。"""
    backups_dir = get_backups_dir()
    return list_backup_paths(uuid_str, Path(backups_dir))
