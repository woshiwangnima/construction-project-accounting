from __future__ import annotations

import copy
import re
from pathlib import Path


IGNORED_TOP_LEVEL_KEYS = {"status", "last_modified", "view_state", "app_version", "schema_version"}
IGNORED_BILL_KEYS = {"record_time", "reviewed"}


def build_backup_fingerprint(data: dict) -> dict:
    """Return project data with volatile fields removed for backup comparison."""
    normalized = copy.deepcopy(data or {})
    for key in IGNORED_TOP_LEVEL_KEYS:
        normalized.pop(key, None)
    for bill in normalized.get("bills") or []:
        if isinstance(bill, dict):
            for key in IGNORED_BILL_KEYS:
                bill.pop(key, None)
    return normalized


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
    sequence_paths: list[tuple[int, Path]] = []
    legacy_paths: list[Path] = []
    for path in backups_dir.iterdir():
        if not path.is_file() or path.suffix != ".json":
            continue
        seq = _extract_sequence(path, stem)
        if seq is not None:
            sequence_paths.append((seq, path))
        elif path.name.startswith(f"{stem}_"):
            legacy_paths.append(path)
    sequence_paths.sort(key=lambda item: item[0], reverse=True)
    legacy_paths.sort(key=lambda path: path.name, reverse=True)
    return [path for _seq, path in sequence_paths] + legacy_paths


def rotate_sequence_backups(project_path: Path, backups_dir: Path, keep_count: int) -> None:
    stem = Path(project_path).stem
    paths: list[tuple[int, Path]] = []
    for path in Path(backups_dir).glob(f"{stem}.*.json"):
        seq = _extract_sequence(path, stem)
        if seq is not None:
            paths.append((seq, path))
    paths.sort(key=lambda item: item[0], reverse=True)
    for _seq, path in paths[max(1, keep_count):]:
        path.unlink(missing_ok=True)


def make_room_for_backup(project_path: Path, backups_dir: Path, max_count: int) -> None:
    """按文件修改时间删除最老备份，使序列备份数 < max_count。

    配合 _backup_project 的"先删后建"策略使用。
    按 mtime 排序（而非序列号）以避免循环复用序号后认错新旧关系。
    """
    stem = Path(project_path).stem
    seq_paths: list[tuple[int, Path]] = []
    for path in Path(backups_dir).glob(f"{stem}.*.json"):
        seq = _extract_sequence(path, stem)
        if seq is not None:
            seq_paths.append((seq, path))
    if len(seq_paths) < max_count:
        return
    seq_paths.sort(key=lambda item: item[1].stat().st_mtime)
    for _seq, path in seq_paths[:len(seq_paths) - max_count + 1]:
        try:
            path.unlink(missing_ok=True)
        except OSError:
            pass


def _extract_sequence(path: Path, stem: str) -> int | None:
    match = re.fullmatch(rf"{re.escape(stem)}\.(\d+)\.json", path.name)
    if not match:
        return None
    return int(match.group(1))
