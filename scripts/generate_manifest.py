"""Generate a SHA-256 file manifest for a PyInstaller output directory."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from pathlib import Path


MANIFEST_NAME = "file_manifest.json"


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _iter_manifest_files(build_dir: Path):
    for path in sorted(build_dir.rglob("*"), key=lambda item: item.as_posix()):
        if path.name == MANIFEST_NAME:
            continue
        if path.is_symlink():
            raise ValueError(f"symlinks are not supported in release output: {path}")
        if path.is_file():
            yield path


def generate_manifest(build_dir: Path, version: str = "", platform: str = "") -> dict:
    build_dir = build_dir.resolve()
    manifest: dict = {"version": version, "platform": platform, "files": {}}
    for path in _iter_manifest_files(build_dir):
        relative = path.relative_to(build_dir).as_posix()
        manifest["files"][relative] = sha256_file(path)
    return manifest


def _write_manifest(path: Path, manifest: dict) -> None:
    temporary = path.with_name(f".{path.name}.tmp")
    try:
        with temporary.open("w", encoding="utf-8", newline="\n") as handle:
            json.dump(manifest, handle, indent=2, ensure_ascii=False)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        if temporary.exists():
            temporary.unlink()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("build_dir", type=Path, help="PyInstaller output directory")
    parser.add_argument("--version", default="", help="release version, for example 1.0.1")
    parser.add_argument("--platform", default="", help="release platform, for example win64")
    args = parser.parse_args(argv)

    build_dir = args.build_dir.resolve()
    if not build_dir.is_dir():
        print(f"[ERROR] directory not found: {build_dir}", file=sys.stderr)
        return 1

    try:
        manifest = generate_manifest(build_dir, args.version, args.platform)
        destination = build_dir / MANIFEST_NAME
        _write_manifest(destination, manifest)
    except (OSError, ValueError) as exc:
        print(f"[ERROR] could not generate manifest: {exc}", file=sys.stderr)
        return 1

    print(f"Manifest generated: {len(manifest['files'])} files -> {destination}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
