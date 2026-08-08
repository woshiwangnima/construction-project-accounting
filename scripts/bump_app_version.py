"""Update the canonical application version and optional runtime JSON data.

Usage:
    python scripts/bump_app_version.py 1.0.2
    python scripts/bump_app_version.py 1.0.2 --include-data --data-dir C:\\Users\\me\\AppData

The source constant and bundled app configuration are always updated. Runtime
projects, backups, and user configuration are changed only when explicitly
requested with ``--include-data``.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
VERSION_FILE = ROOT / "src" / "versioning.py"
RESOURCE_CONFIG = ROOT / "config" / "app_config.json"
VERSION_RE = re.compile(r"^[0-9]+\.[0-9]+\.[0-9]+(?:[-+][0-9A-Za-z.-]+)?$")
SOURCE_VERSION_RE = re.compile(
    r"(?m)^(?P<prefix>APP_VERSION\s*=\s*)(?P<quote>[\"'])(?P<version>[^\"']+)(?P=quote)(?P<suffix>\s*)$"
)


def validate_version(version: str) -> None:
    if not VERSION_RE.fullmatch(version):
        raise ValueError(f"invalid semantic version: {version!r}")


def _atomic_write_text(path: Path, text: str) -> None:
    temporary: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=path.parent,
            prefix=f".{path.name}.",
            suffix=".tmp",
            delete=False,
        ) as handle:
            temporary = Path(handle.name)
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
        temporary = None
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def update_source_version(new_version: str) -> tuple[str, str] | None:
    text = VERSION_FILE.read_text(encoding="utf-8")
    matches = list(SOURCE_VERSION_RE.finditer(text))
    if len(matches) != 1:
        raise RuntimeError(f"expected one APP_VERSION assignment in {VERSION_FILE}")

    match = matches[0]
    old_version = match.group("version")
    if old_version == new_version:
        return None

    replacement = (
        f"{match.group('prefix')}\"{new_version}\"{match.group('suffix')}"
    )
    _atomic_write_text(VERSION_FILE, text[:match.start()] + replacement + text[match.end():])
    return old_version, new_version


def update_version_in_file(path: Path, new_version: str) -> tuple[str, str] | None:
    with path.open(encoding="utf-8") as handle:
        data = json.load(handle)
    if not isinstance(data, dict) or "app_version" not in data:
        return None

    old_version = str(data["app_version"])
    if old_version == new_version:
        return None

    data["app_version"] = new_version
    serialized = json.dumps(data, ensure_ascii=False, indent=2) + "\n"
    _atomic_write_text(path, serialized)
    return old_version, new_version


def scan_directory(directory: Path, new_version: str, label: str) -> int:
    if not directory.is_dir():
        print(f"  [skip] {label}: directory does not exist: {directory}")
        return 0

    count = 0
    for path in sorted(directory.glob("*.json")):
        if not path.is_file():
            continue
        try:
            result = update_version_in_file(path, new_version)
        except (OSError, json.JSONDecodeError, UnicodeError) as exc:
            print(f"  [error] {path}: {exc}", file=sys.stderr)
            continue
        if result is None:
            continue
        old_version, _ = result
        print(f"  [updated] {path}: {old_version} -> {new_version}")
        count += 1
    return count


def _default_data_dir() -> Path:
    configured = os.environ.get("CPA_DATA_DIR", "").strip()
    if configured:
        return Path(configured).expanduser()
    if os.name == "nt":
        root = os.environ.get("APPDATA") or os.environ.get("LOCALAPPDATA")
        if root:
            return Path(root) / "ConstructionAccounting"
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / "ConstructionAccounting"
    return Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share")) / "ConstructionAccounting"


def update_runtime_data(new_version: str, data_dir: Path) -> int:
    total = 0
    config_dir = Path(os.environ.get("CPA_CONFIG_DIR", data_dir / "config"))
    projects_dir = Path(os.environ.get("CPA_PROJECTS_DIR", data_dir / "projects"))
    backups_dir = Path(os.environ.get("CPA_BACKUPS_DIR", data_dir / "backups"))

    user_config = config_dir / "user_config.json"
    if user_config.is_file():
        try:
            result = update_version_in_file(user_config, new_version)
        except (OSError, json.JSONDecodeError, UnicodeError) as exc:
            print(f"  [error] {user_config}: {exc}", file=sys.stderr)
        else:
            if result:
                print(f"  [updated] {user_config}: {result[0]} -> {new_version}")
                total += 1

    total += scan_directory(projects_dir, new_version, "projects")
    total += scan_directory(backups_dir, new_version, "backups")
    return total


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("version", help="new semantic version, for example 1.0.2")
    parser.add_argument(
        "--include-data",
        action="store_true",
        help="also update user config, projects, and backups in the runtime data directory",
    )
    parser.add_argument(
        "--data-dir",
        type=Path,
        help="runtime data directory used with --include-data (defaults to CPA_DATA_DIR/OS default)",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        validate_version(args.version)
        source_result = update_source_version(args.version)
        resource_result = update_version_in_file(RESOURCE_CONFIG, args.version)
    except (OSError, UnicodeError, json.JSONDecodeError, RuntimeError, ValueError) as exc:
        print(f"Version update failed: {exc}", file=sys.stderr)
        return 1

    print(f"Target version: {args.version}")
    if source_result:
        print(f"  [updated] {VERSION_FILE}: {source_result[0]} -> {args.version}")
    else:
        print(f"  [skip] {VERSION_FILE}: already {args.version}")
    if resource_result:
        print(f"  [updated] {RESOURCE_CONFIG}: {resource_result[0]} -> {args.version}")
    else:
        print(f"  [skip] {RESOURCE_CONFIG}: already {args.version}")

    if args.include_data:
        data_dir = args.data_dir.expanduser() if args.data_dir else _default_data_dir()
        print(f"Runtime data: {data_dir}")
        total = update_runtime_data(args.version, data_dir)
        print(f"Updated runtime files: {total}")
    else:
        print("Runtime data skipped; pass --include-data to update it.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
