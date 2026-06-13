"""为 PyInstaller build 输出目录生成 SHA256 file_manifest.json。

用法: python scripts/generate_manifest.py <build_dir> [--version X.Y.Z]
"""
import argparse
import hashlib
import json
import sys
from pathlib import Path


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def generate_manifest(build_dir: Path, version: str = "") -> dict:
    manifest: dict = {"version": version, "files": {}}
    for p in sorted(build_dir.rglob("*")):
        if not p.is_file():
            continue
        if p.name in ("file_manifest.json",):
            continue
        rel = p.relative_to(build_dir).as_posix()
        manifest["files"][rel] = sha256_file(p)
    return manifest


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("build_dir", type=Path, help="dist/ConstructionAccounting/ 路径")
    parser.add_argument("--version", default="", help="版本号，例如 1.0.0")
    args = parser.parse_args()

    build_dir: Path = args.build_dir
    if not build_dir.is_dir():
        print(f"错误：目录不存在 {build_dir}", file=sys.stderr)
        sys.exit(1)

    manifest = generate_manifest(build_dir, args.version)
    dest = build_dir / "file_manifest.json"
    with open(dest, "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2, ensure_ascii=False)
    print(f"manifest 生成完毕：{len(manifest['files'])} 个文件 → {dest}")


if __name__ == "__main__":
    main()
