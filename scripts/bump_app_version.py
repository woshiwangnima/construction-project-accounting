"""批量更新 user_config、项目文件、备份文件中的 app_version 字段。

用法：
    python scripts/bump_app_version.py <新版本号>

示例：
    python scripts/bump_app_version.py 1.0.1
"""
import json
import os
import sys
from pathlib import Path

# 项目根目录（scripts/ 的上一级）
ROOT = Path(__file__).resolve().parent.parent

CONFIG_DIR = ROOT / "config"
PROJECTS_DIR = ROOT / "projects"
BACKUPS_DIR = ROOT / "backups"


def update_version_in_file(path: Path, new_version: str) -> tuple[str, str] | None:
    """读取 JSON 文件，更新 app_version 字段，写回。

    返回 (old_version, new_version) 或 None（无 app_version 字段时）。
    """
    with path.open(encoding="utf-8") as f:
        data = json.load(f)

    if not isinstance(data, dict):
        return None

    old = data.get("app_version")
    if old is None:
        return None

    if old == new_version:
        return None

    data["app_version"] = new_version

    # 写回（先 tmp 再 rename，保证原子性）
    tmp = path.with_suffix(".tmp")
    with tmp.open("w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
        f.write("\n")
    os.replace(str(tmp), str(path))

    return (str(old), new_version)


def scan_directory(directory: Path, new_version: str, label: str) -> int:
    """扫描目录下所有 .json 文件，更新 app_version。返回更新数量。"""
    if not directory.is_dir():
        print(f"  [跳过] {label} 目录不存在: {directory}")
        return 0

    count = 0
    for path in sorted(directory.glob("*.json")):
        if not path.is_file():
            continue
        result = update_version_in_file(path, new_version)
        if result is None:
            continue
        old, new = result
        print(f"  [更新] {path.relative_to(ROOT)}  {old} -> {new}")
        count += 1

    return count


def main():
    if len(sys.argv) < 2:
        print("用法: python scripts/bump_app_version.py <新版本号>")
        print("示例: python scripts/bump_app_version.py 1.0.1")
        sys.exit(1)

    new_version = sys.argv[1]
    print(f"目标版本: {new_version}")
    print(f"项目根目录: {ROOT}")
    print()

    total = 0

    # 1. user_config.json
    print("── user_config ──")
    uc = CONFIG_DIR / "user_config.json"
    if uc.is_file():
        result = update_version_in_file(uc, new_version)
        if result:
            old, new = result
            print(f"  [更新] config/user_config.json  {old} -> {new}")
            total += 1
        else:
            print(f"  [跳过] config/user_config.json  已是 {new_version} 或无 app_version 字段")
    else:
        print(f"  [跳过] config/user_config.json  文件不存在")
    print()

    # 2. projects/
    print("── projects ──")
    total += scan_directory(PROJECTS_DIR, new_version, "projects")
    print()

    # 3. backups/
    print("── backups ──")
    total += scan_directory(BACKUPS_DIR, new_version, "backups")
    print()

    print(f"完成，共更新 {total} 个文件。")


if __name__ == "__main__":
    main()
