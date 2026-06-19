#!/usr/bin/env python3
"""迁移脚本：为所有项目和备份文件补充 description 字段。"""
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src.utils import atomic_write_json
from src.project_uuid import get_projects_dir, get_backups_dir
from src.logger import logger


def _ensure_description(filepath: str) -> bool:
    """如果文件缺少 description 字段则补充。返回是否修改。"""
    try:
        with open(filepath, encoding="utf-8") as f:
            data = json.load(f)
    except (json.JSONDecodeError, OSError) as e:
        logger.warning("跳过无法读取的文件 %s: %s", filepath, e)
        return False
    if "description" in data:
        return False
    data["description"] = ""
    atomic_write_json(filepath, data)
    logger.info("已补充 description 字段: %s", filepath)
    return True


def main():
    count = 0
    for base_dir in (get_projects_dir(), get_backups_dir()):
        if not os.path.isdir(base_dir):
            logger.info("目录不存在，跳过: %s", base_dir)
            continue
        for fname in os.listdir(base_dir):
            if not fname.endswith(".json"):
                continue
            path = os.path.join(base_dir, fname)
            if _ensure_description(path):
                count += 1
    print(f"迁移完成，共修改 {count} 个文件。")


if __name__ == "__main__":
    main()
