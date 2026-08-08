"""应用资源目录与用户数据目录。

打包资源是只读的；项目、备份、日志和用户配置属于运行时数据，默认放到
操作系统的用户数据目录。CPA_* 环境变量仍可覆盖各目录，便于开发和迁移。
"""
from __future__ import annotations

import os
import shutil
import sys
import tempfile
from pathlib import Path


APP_NAME = "ConstructionAccounting"
PACKAGE_ROOT = Path(__file__).resolve().parent.parent


def get_resource_root() -> Path:
    """返回随程序发布的只读资源根目录。"""
    if getattr(sys, "frozen", False):
        return Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent))
    return PACKAGE_ROOT


def get_legacy_root() -> Path:
    """返回旧版本在仓库/安装目录中保存数据的位置。"""
    return PACKAGE_ROOT


def _default_user_data_dir() -> Path:
    if sys.platform == "win32":
        root = os.environ.get("APPDATA") or os.environ.get("LOCALAPPDATA")
        if root:
            return Path(root) / APP_NAME
    elif sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / APP_NAME
    else:
        root = os.environ.get("XDG_DATA_HOME")
        if root:
            return Path(root) / APP_NAME
        return Path.home() / ".local" / "share" / APP_NAME
    return Path.home() / f".{APP_NAME.lower()}"


def _env_path(name: str, fallback: Path) -> Path:
    value = os.environ.get(name, "").strip()
    path = Path(value).expanduser() if value else Path(fallback).expanduser()
    # A relative override would make the data location depend on the process
    # working directory, which can defeat the single-instance lock when the
    # app is launched from different shortcuts.
    return path.absolute()


def get_data_dir() -> Path:
    return _env_path("CPA_DATA_DIR", _default_user_data_dir())


def get_config_dir() -> Path:
    return _env_path("CPA_CONFIG_DIR", get_data_dir() / "config")


def get_projects_dir() -> Path:
    return _env_path("CPA_PROJECTS_DIR", get_data_dir() / "projects")


def get_backups_dir() -> Path:
    return _env_path("CPA_BACKUPS_DIR", get_data_dir() / "backups")


def get_migration_backups_dir() -> Path:
    return _env_path("CPA_MIGRATION_BACKUPS_DIR", get_data_dir() / "migration_backups")


def get_log_dir() -> Path:
    return _env_path("CPA_LOG_DIR", get_data_dir() / "logs")


def get_resource_config_dir() -> Path:
    return get_resource_root() / "config"


def migrate_legacy_data() -> tuple[int, list[str]]:
    """首次切换到用户目录时复制旧版运行数据，不删除旧文件。

    显式指定 CPA_DATA_DIR 的用户通常正在做自定义部署，因此不自动复制。
    迁移使用“只复制不存在的目标文件”策略，失败时不写完成标记，便于下次重试。
    """
    if os.environ.get("CPA_DATA_DIR"):
        return 0, []

    data_dir = get_data_dir()
    legacy_root = get_legacy_root()
    try:
        data_root = data_dir.resolve()
        legacy_root = legacy_root.resolve()
        if data_root == legacy_root:
            return 0, []
    except OSError:
        return 0, []

    # Never recursively copy a data tree into itself (or copy the package
    # tree into one of its parents). This can otherwise duplicate files on
    # every startup and can cross an unintended symlink boundary.
    if _paths_overlap(data_root, legacy_root):
        return 0, [f"legacy migration skipped because paths overlap: {legacy_root} / {data_root}"]

    marker = data_dir / ".legacy_migration_v1"
    if marker.exists():
        return 0, []

    copied = 0
    failures: list[str] = []
    for relative in ("config", "projects", "backups", "migration_backups"):
        source_dir = legacy_root / relative
        if source_dir.is_symlink() or not source_dir.is_dir():
            continue
        for source in source_dir.rglob("*"):
            if source.is_symlink() or not source.is_file():
                continue
            target = data_dir / relative / source.relative_to(source_dir)
            if os.path.lexists(target):
                continue
            try:
                target.parent.resolve().relative_to(data_root)
            except (OSError, ValueError) as exc:
                failures.append(f"{target}: unsafe migration target ({exc})")
                continue
            try:
                target.parent.mkdir(parents=True, exist_ok=True)
                _copy_file_atomically(source, target)
                copied += 1
            except OSError as exc:
                failures.append(f"{source}: {exc}")

    if not failures:
        try:
            data_dir.mkdir(parents=True, exist_ok=True)
            _write_marker_atomically(marker)
        except OSError as exc:
            failures.append(f"{marker}: {exc}")
    return copied, failures


def _paths_overlap(first: Path, second: Path) -> bool:
    try:
        first.relative_to(second)
        return True
    except ValueError:
        pass
    try:
        second.relative_to(first)
        return True
    except ValueError:
        return False


def _copy_file_atomically(source: Path, target: Path) -> None:
    fd, temp_name = tempfile.mkstemp(
        prefix=f".{target.name}.",
        suffix=".tmp",
        dir=str(target.parent),
    )
    os.close(fd)
    temp_path = Path(temp_name)
    try:
        shutil.copy2(source, temp_path)
        os.replace(temp_path, target)
    finally:
        try:
            temp_path.unlink(missing_ok=True)
        except OSError:
            pass


def _write_marker_atomically(marker: Path) -> None:
    fd, temp_name = tempfile.mkstemp(
        prefix=".legacy_migration.",
        suffix=".tmp",
        dir=str(marker.parent),
    )
    temp_path = Path(temp_name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            stream.write("legacy data migrated\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temp_path, marker)
    finally:
        try:
            temp_path.unlink(missing_ok=True)
        except OSError:
            pass
