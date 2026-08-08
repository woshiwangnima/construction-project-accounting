from __future__ import annotations

import json
import re
from pathlib import Path


IGNORED_TOP_LEVEL_KEYS = {"status", "last_modified", "view_state", "app_version", "schema_version"}
IGNORED_BILL_KEYS = {"record_time", "reviewed"}


def build_backup_fingerprint(data: dict) -> str:
    """去除易变字段后规范序列化为字符串，用于备份比较。

    直接过滤并序列化，避免 deepcopy 大项目数据的开销；确定性排序保证
    仅键值变化时才产生差异。
    """
    if not isinstance(data, dict):
        data = {}
    normalized = {k: v for k, v in data.items() if k not in IGNORED_TOP_LEVEL_KEYS}
    bills = normalized.get("bills")
    if isinstance(bills, list):
        filtered = []
        for bill in bills:
            if isinstance(bill, dict):
                filtered.append({k: v for k, v in bill.items() if k not in IGNORED_BILL_KEYS})
            else:
                filtered.append(bill)
        normalized["bills"] = filtered
    return json.dumps(normalized, sort_keys=True, ensure_ascii=False, default=str)


def should_backup(before: dict, after: dict) -> bool:
    return build_backup_fingerprint(before) != build_backup_fingerprint(after)


def next_sequence_backup_path(project_path: Path, backups_dir: Path) -> Path:
    backups_dir = Path(backups_dir)
    stem = Path(project_path).stem
    used: set[int] = set()
    for path in backups_dir.glob(f"{stem}.*.json"):
        seq = _extract_sequence(path, stem)
        if seq is not None:
            used.add(seq)
    seq = 1
    while seq in used:
        seq += 1
    return backups_dir / f"{stem}.{seq}.json"


def list_backup_paths(project_uuid: str, backups_dir: Path) -> list[Path]:
    backups_dir = Path(backups_dir)
    if not backups_dir.is_dir():
        return []
    stem = f"p_{project_uuid}"
    paths: list[Path] = []
    for path in backups_dir.iterdir():
        if path.is_symlink() or not path.is_file() or path.suffix != ".json":
            continue
        seq = _extract_sequence(path, stem)
        if seq is not None or _is_legacy_backup_name(path, stem):
            paths.append(path)
    return sorted(paths, key=_mtime_key, reverse=True)


def rotate_sequence_backups(
    project_path: Path, backups_dir: Path, keep_count: int, max_total_bytes: int = 0
) -> None:
    """轮换备份：保留最新 keep_count 条；若总字节超 max_total_bytes，再删最老备份。

    按 mtime（而非序列号）判断新旧，避免序号循环复用后认错关系。
    删除失败仅记录（忽略），不影响新备份与项目保存。
    """
    paths = _all_backup_paths(project_path, backups_dir)
    keep = max(1, keep_count)
    if len(paths) > keep:
        for path in paths[keep:]:
            _unlink(path)
    if max_total_bytes > 0:
        kept = paths[:keep]
        total = sum(_file_size(p) for p in kept)
        # 从最老备份开始删，直到满足字节上限（至少保留 1 条）
        while total > max_total_bytes and len(kept) > 1:
            oldest = kept.pop()
            size = _file_size(oldest)
            if _unlink(oldest):
                total -= size


def _unlink(path: Path) -> bool:
    try:
        path.unlink(missing_ok=True)
        return True
    except OSError:
        return False


def _file_size(path: Path) -> int:
    try:
        return path.stat().st_size
    except OSError:
        return 0


def _all_backup_paths(project_path: Path, backups_dir: Path) -> list[Path]:
    stem = Path(project_path).stem
    result: list[Path] = []
    for path in Path(backups_dir).iterdir() if Path(backups_dir).is_dir() else []:
        if path.is_symlink() or not path.is_file() or path.suffix != ".json":
            continue
        if _extract_sequence(path, stem) is not None or _is_legacy_backup_name(path, stem):
            result.append(path)
    return sorted(result, key=_mtime_key, reverse=True)


def _mtime_key(path: Path) -> tuple[int, str]:
    try:
        return (path.stat().st_mtime_ns, path.name)
    except OSError:
        return (0, path.name)


def _is_legacy_backup_name(path: Path, stem: str) -> bool:
    """Recognize historical date-based backup names only.

    Cleanup must not treat an arbitrary ``p_<id>_*.json`` file as a backup;
    otherwise a user-created export with the same prefix could be deleted.
    ``migrate_v3`` may append microseconds, so an optional numeric suffix is
    accepted after the normal ``YYYYMMDD_HHMMSS`` timestamp.
    """
    return re.fullmatch(
        rf"{re.escape(stem)}_\d{{8}}_\d{{6}}(?:_\d+)?\.json",
        path.name,
    ) is not None


def _extract_sequence(path: Path, stem: str) -> int | None:
    match = re.fullmatch(rf"{re.escape(stem)}\.(\d+)\.json", path.name)
    if not match:
        return None
    return int(match.group(1))
