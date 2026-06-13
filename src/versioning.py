from __future__ import annotations

import json
import os
import shutil
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Callable

from .logger import logger
from .utils import atomic_write_json


APP_VERSION = "1.0.1"
CURRENT_SCHEMA_VERSION = 1


class MigrationError(RuntimeError):
    pass


@dataclass(frozen=True)
class MigrationResult:
    path: Path
    kind: str
    original_schema_version: int | None
    target_schema_version: int
    changed: bool
    backup_path: Path | None = None
    error: str | None = None


def schema_version_of(data: dict) -> int:
    try:
        return int(data.get("schema_version", 0) or 0)
    except (TypeError, ValueError):
        return 0


def _migrate_0_to_1(data: dict) -> dict:
    migrated = dict(data)
    migrated.setdefault("app_version", APP_VERSION)
    migrated["schema_version"] = 1
    return migrated


MigrationFunc = Callable[[dict], dict]

MIGRATIONS: dict[str, dict[int, MigrationFunc]] = {
    "app_config": {0: _migrate_0_to_1},
    "user_config": {0: _migrate_0_to_1},
    "project": {0: _migrate_0_to_1},
    "backup": {0: _migrate_0_to_1},
}


# ── 迁移原语（Migration Primitives）──────────────────────
# 在编写 _migrate_N_to_M 函数时组合使用这些原语，
# 每个原语都返回 data 本身以支持链式调用。

def _resolve_path(data: dict, nested: tuple[str, ...] | None) -> dict:
    """沿 nested 路径向下导航，返回目标 dict。路径不存在时返回空 dict。"""
    if not nested:
        return data
    current = data
    for key in nested:
        if isinstance(current, dict) and key in current and isinstance(current[key], dict):
            current = current[key]
        else:
            return {}
    return current


def rename_field(data: dict, old_key: str, new_key: str, *,
                 nested: tuple[str, ...] | None = None) -> dict:
    """重命名字段。nested 指定嵌套路径，如 ("export_defaults",)。"""
    target = _resolve_path(data, nested)
    if old_key in target and new_key not in target:
        target[new_key] = target.pop(old_key)
    return data


def set_default(data: dict, key: str, default, *,
                nested: tuple[str, ...] | None = None) -> dict:
    """如果字段不存在，注入默认值。"""
    target = _resolve_path(data, nested)
    if key not in target:
        target[key] = default
    return data


def change_type(data: dict, key: str, converter: Callable, *,
                nested: tuple[str, ...] | None = None) -> dict:
    """转换字段类型，如 str→int、list→dict。converter 接收旧值返回新值。"""
    target = _resolve_path(data, nested)
    if key in target:
        try:
            target[key] = converter(target[key])
        except (TypeError, ValueError):
            pass
    return data


def remove_field(data: dict, key: str, *,
                 nested: tuple[str, ...] | None = None) -> dict:
    """删除废弃字段。"""
    target = _resolve_path(data, nested)
    target.pop(key, None)
    return data


def transform_each(data: dict, list_key: str, transform_fn: Callable[[dict], dict], *,
                   nested: tuple[str, ...] | None = None) -> dict:
    """对列表中每个 dict 元素执行变换（如 bills、trade_items）。"""
    target = _resolve_path(data, nested)
    if list_key in target and isinstance(target[list_key], list):
        target[list_key] = [
            transform_fn(item) if isinstance(item, dict) else item
            for item in target[list_key]
        ]
    return data


def migrate_json_document(kind: str, data: dict) -> dict:
    if kind not in MIGRATIONS:
        raise MigrationError(f"Unknown migration kind: {kind}")
    current = schema_version_of(data)
    if current == CURRENT_SCHEMA_VERSION:
        return dict(data)
    if current > CURRENT_SCHEMA_VERSION:
        raise MigrationError(f"Unsupported future schema version {current} for {kind}")

    migrated = dict(data)
    while current < CURRENT_SCHEMA_VERSION:
        step = MIGRATIONS[kind].get(current)
        if step is None:
            raise MigrationError(f"Missing migration for {kind} schema {current} -> {current + 1}")
        migrated = step(migrated)
        current = schema_version_of(migrated)
    return migrated


def _default_batch_id() -> str:
    return datetime.now().strftime("%Y%m%d_%H%M%S")


def _relative_backup_path(path: Path, kind: str) -> Path:
    if kind in ("app_config", "user_config"):
        return Path("config") / path.name
    if kind == "project":
        return Path("projects") / path.name
    if kind == "backup":
        return Path("backups") / path.name
    return Path(kind) / path.name


def migrate_json_file(path: str | Path, kind: str, *, backup_root: str | Path | None = None,
                      batch_id: str | None = None) -> MigrationResult:
    path = Path(path)
    backup_root = Path(backup_root) if backup_root is not None else Path("migration_backups")
    batch_id = batch_id or _default_batch_id()
    try:
        with path.open(encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, json.JSONDecodeError) as e:
        logger.error("Migration skipped path=%s kind=%s error=%s", path, kind, e)
        return MigrationResult(path, kind, None, CURRENT_SCHEMA_VERSION, changed=False, error=str(e))
    if not isinstance(data, dict):
        msg = "JSON root is not an object"
        logger.error("Migration skipped path=%s kind=%s error=%s", path, kind, msg)
        return MigrationResult(path, kind, None, CURRENT_SCHEMA_VERSION, changed=False, error=msg)

    original_version = schema_version_of(data)
    try:
        migrated = migrate_json_document(kind, data)
    except MigrationError as e:
        logger.error("Migration failed path=%s kind=%s schema=%s error=%s", path, kind, original_version, e)
        return MigrationResult(path, kind, original_version, CURRENT_SCHEMA_VERSION, changed=False, error=str(e))

    if migrated == data:
        logger.debug("Migration skipped current path=%s kind=%s schema=%s", path, kind, original_version)
        return MigrationResult(path, kind, original_version, CURRENT_SCHEMA_VERSION, changed=False)

    backup_path = backup_root / batch_id / _relative_backup_path(path, kind)
    backup_path.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(path, backup_path)
    atomic_write_json(str(path), migrated)
    logger.info("Migrated path=%s kind=%s schema=%s->%s backup=%s",
                path, kind, original_version, CURRENT_SCHEMA_VERSION, backup_path)
    return MigrationResult(path, kind, original_version, CURRENT_SCHEMA_VERSION,
                           changed=True, backup_path=backup_path)


def _json_files(directory: str | Path) -> list[Path]:
    directory = Path(directory)
    if not directory.is_dir():
        return []
    return sorted(p for p in directory.glob("*.json") if p.is_file())


def migrate_all_known_files(*, config_dir: str | Path | None = None,
                            projects_dir: str | Path | None = None,
                            backups_dir: str | Path | None = None,
                            backup_root: str | Path | None = None,
                            batch_id: str | None = None) -> list[MigrationResult]:
    base_dir = Path(__file__).resolve().parent.parent
    config_dir = Path(config_dir) if config_dir is not None else Path(os.environ.get("CPA_CONFIG_DIR", base_dir / "config"))
    projects_dir = Path(projects_dir) if projects_dir is not None else Path(os.environ.get("CPA_PROJECTS_DIR", base_dir / "projects"))
    backups_dir = Path(backups_dir) if backups_dir is not None else Path(os.environ.get("CPA_BACKUPS_DIR", base_dir / "backups"))
    backup_root = Path(backup_root) if backup_root is not None else base_dir / "migration_backups"
    batch_id = batch_id or _default_batch_id()

    targets: list[tuple[Path, str]] = []
    targets.append((config_dir / "app_config.json", "app_config"))
    targets.append((config_dir / "user_config.json", "user_config"))
    targets.extend((p, "project") for p in _json_files(projects_dir))
    targets.extend((p, "backup") for p in _json_files(backups_dir))

    results: list[MigrationResult] = []
    for path, kind in targets:
        if not path.exists():
            continue
        results.append(migrate_json_file(path, kind, backup_root=backup_root, batch_id=batch_id))
    changed = sum(1 for r in results if r.changed)
    failed = sum(1 for r in results if r.error)
    logger.info("Migration summary checked=%s changed=%s failed=%s", len(results), changed, failed)
    return results


def rollback_migration_batch(batch_id: str, *,
                             backup_root: str | Path | None = None) -> list[str]:
    """将指定批次迁移的所有文件恢复到迁移前的状态。

    返回已恢复的文件路径列表。如果没有找到批次备份，返回空列表。
    """
    base_dir = Path(__file__).resolve().parent.parent
    backup_root = Path(backup_root) if backup_root is not None else base_dir / "migration_backups"
    batch_dir = backup_root / batch_id
    if not batch_dir.is_dir():
        logger.warning("rollback: batch_id=%s not found at %s", batch_id, batch_dir)
        return []

    restored: list[str] = []
    for backup_file in sorted(batch_dir.rglob("*.json")):
        relative = backup_file.relative_to(batch_dir)
        original = base_dir / relative
        try:
            original.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(backup_file, original)
            restored.append(str(original))
            logger.info("rollback: restored %s from %s", original, backup_file)
        except OSError as e:
            logger.error("rollback: failed to restore %s: %s", original, e)

    logger.info("rollback: batch=%s restored=%d files", batch_id, len(restored))
    return restored


def main() -> None:
    results = migrate_all_known_files()
    changed = sum(1 for r in results if r.changed)
    failed = sum(1 for r in results if r.error)
    print(f"Migration checked={len(results)} changed={changed} failed={failed}")


if __name__ == "__main__":
    main()
