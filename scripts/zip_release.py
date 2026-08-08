"""Validate and create a release ZIP for a PyInstaller output directory."""

from __future__ import annotations

import hashlib
import json
import os
import re
import sys
import zipfile
from pathlib import Path, PurePosixPath


MANIFEST_NAME = "file_manifest.json"
REQUIRED_FILES = (
    "ConstructionAccounting.exe",
    "config/app_config.json",
)
VERSION_RE = re.compile(r"^[0-9]+\.[0-9]+\.[0-9]+(?:[-+][0-9A-Za-z.-]+)?$")
PLATFORM_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
HASH_RE = re.compile(r"^[0-9a-fA-F]{64}$")


def read_source_version() -> str:
    version_file = Path(__file__).resolve().parent.parent / "src" / "versioning.py"
    marker = "APP_VERSION = "
    for line in version_file.read_text(encoding="utf-8").splitlines():
        if line.startswith(marker):
            return line.split("=", 1)[1].strip().strip("\"'")
    raise RuntimeError(f"APP_VERSION not found in {version_file}")


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _relative_files(build_dir: Path) -> set[str]:
    files: set[str] = set()
    for path in build_dir.rglob("*"):
        if path.name == MANIFEST_NAME:
            continue
        if path.is_symlink():
            raise ValueError(f"symlinks are not supported in release output: {path}")
        if path.is_file():
            files.add(path.relative_to(build_dir).as_posix())
    return files


def _normalise_manifest_path(value: str) -> str:
    if not value or "\\" in value:
        raise ValueError(f"invalid manifest path: {value!r}")
    path = PurePosixPath(value)
    if path.is_absolute() or ".." in path.parts or path.as_posix() != value:
        raise ValueError(f"invalid manifest path: {value!r}")
    return value


def _load_manifest(build_dir: Path) -> tuple[dict, dict[str, str]]:
    manifest_path = build_dir / MANIFEST_NAME
    if not manifest_path.is_file():
        raise ValueError(f"missing {MANIFEST_NAME}")
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"invalid {MANIFEST_NAME}: {exc}") from exc

    if not isinstance(manifest, dict) or not isinstance(manifest.get("files"), dict):
        raise ValueError("manifest must contain a files object")

    expected: dict[str, str] = {}
    for relative, digest in manifest["files"].items():
        if not isinstance(relative, str) or not isinstance(digest, str):
            raise ValueError("manifest entries must be string path/hash pairs")
        relative = _normalise_manifest_path(relative)
        if not HASH_RE.fullmatch(digest):
            raise ValueError(f"invalid SHA-256 hash for {relative}")
        full_path = build_dir.joinpath(*PurePosixPath(relative).parts)
        if not full_path.is_file():
            raise ValueError(f"manifest file is missing: {relative}")
        expected[relative] = digest.lower()

    actual = _relative_files(build_dir)
    if actual != set(expected):
        missing = sorted(set(expected) - actual)
        extra = sorted(actual - set(expected))
        raise ValueError(f"manifest file set mismatch; missing={missing}, extra={extra}")

    for relative, digest in expected.items():
        actual_digest = _sha256_file(build_dir.joinpath(*PurePosixPath(relative).parts))
        if actual_digest != digest:
            raise ValueError(f"manifest hash mismatch: {relative}")
    return manifest, expected


def validate_release_dir(build_dir: Path, version: str = "", platform: str = "") -> dict:
    """Validate required files and the manifest; return the parsed manifest."""

    build_dir = build_dir.resolve()
    if not build_dir.is_dir():
        raise ValueError(f"directory not found: {build_dir}")
    for relative in REQUIRED_FILES:
        if not (build_dir / Path(relative)).is_file():
            raise ValueError(f"required release file is missing: {relative}")
    if not any(
        path.is_file() and path.suffix.lower() == ".wav" and "assets" in path.parts
        for path in build_dir.rglob("*")
    ):
        raise ValueError("release assets are missing: no assets/*.wav file found")

    manifest, _expected = _load_manifest(build_dir)
    if version and manifest.get("version") != version:
        raise ValueError(
            f"manifest version mismatch: expected {version!r}, got {manifest.get('version')!r}"
        )
    if platform and manifest.get("platform") != platform:
        raise ValueError(
            f"manifest platform mismatch: expected {platform!r}, got {manifest.get('platform')!r}"
        )
    return manifest


def _verify_zip(zip_path: Path, expected_files: set[str]) -> None:
    with zipfile.ZipFile(zip_path, "r") as archive:
        names = [info.filename for info in archive.infolist()]
        if len(names) != len(set(names)):
            raise ValueError("release ZIP contains duplicate entries")
        expected_names = expected_files | {MANIFEST_NAME}
        if set(names) != expected_names:
            raise ValueError("release ZIP contents do not match the manifest")
        manifest = json.loads(archive.read(MANIFEST_NAME).decode("utf-8"))
        for relative, digest in manifest["files"].items():
            if hashlib.sha256(archive.read(relative)).hexdigest() != digest.lower():
                raise ValueError(f"release ZIP hash mismatch: {relative}")


def create_release_zip(build_dir: Path, version: str = "", platform: str = "win64") -> Path:
    build_dir = build_dir.resolve()
    version = version or read_source_version()
    if not VERSION_RE.fullmatch(version):
        raise ValueError(f"invalid release version: {version!r}")
    if not PLATFORM_RE.fullmatch(platform):
        raise ValueError(f"invalid release platform: {platform!r}")

    manifest = validate_release_dir(build_dir, version, platform)
    expected_files = set(manifest["files"])
    zip_path = build_dir.parent / f"ConstructionAccounting-{version}-{platform}.zip"
    temporary = zip_path.with_name(f".{zip_path.name}.{os.getpid()}.tmp")

    try:
        with zipfile.ZipFile(temporary, "w", zipfile.ZIP_DEFLATED) as archive:
            for root, dirs, files in os.walk(build_dir):
                dirs.sort()
                files.sort()
                root_path = Path(root)
                for filename in files:
                    if filename == MANIFEST_NAME and root_path != build_dir:
                        continue
                    file_path = root_path / filename
                    relative = file_path.relative_to(build_dir).as_posix()
                    archive.write(file_path, relative)
        _verify_zip(temporary, expected_files)
        os.replace(temporary, zip_path)
    finally:
        if temporary.exists():
            temporary.unlink()
    return zip_path


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if not args:
        print("Usage: python zip_release.py <build_dir> [version] [platform]", file=sys.stderr)
        return 2

    build_dir = Path(args[0])
    version = args[1] if len(args) > 1 and args[1] else ""
    platform = args[2] if len(args) > 2 and args[2] else "win64"
    try:
        zip_path = create_release_zip(build_dir, version, platform)
    except (OSError, ValueError, RuntimeError, zipfile.BadZipFile) as exc:
        print(f"[ERROR] release ZIP was not created: {exc}", file=sys.stderr)
        return 1
    print(f"Created: {zip_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
