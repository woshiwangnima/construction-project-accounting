"""`backup` 命令组：存档列表与检视。"""
from __future__ import annotations

import argparse

from ...backup_inspector import (
    VALIDITY_HAS_ORPHANS,
    VALIDITY_INVALID_JSON,
    inspect_backup,
    list_backups_for,
)
from ..common import backups_dir
from ..errors import InvalidArgument
from ..registry import ArgSpec, CommandSpec, register


def _backup_to_dict(info) -> dict:
    return {
        "path": str(info.path),
        "timestamp": info.timestamp,
        "file_index": info.file_index,
        "validity": info.validity,
        "is_valid_json": bool(info.is_valid_json),
        "has_project_uuid": bool(info.has_project_uuid),
        "orphan_count": info.orphan_count,
        "last_modified": info.last_modified,
        "status": info.status,
        "trade_summary": info.trade_summary,
        "bill_summary": info.bill_summary,
        "size": info.path.stat().st_size if info.path.exists() else 0,
    }


def _backup_list(args: argparse.Namespace) -> dict:
    try:
        backups = list_backups_for(args.uuid)
    except Exception as exc:
        raise InvalidArgument(f"无法读取备份: {exc}", details={"uuid": args.uuid}) from exc

    items = [_backup_to_dict(info) for info in backups]
    if args.valid_only:
        items = [b for b in items if b["is_valid_json"]]
    return {
        "uuid": args.uuid,
        "count": len(items),
        "backups_dir": str(backups_dir()),
        "backups": items,
    }


def _backup_inspect(args: argparse.Namespace) -> dict:
    info = inspect_backup(args.path)
    payload = _backup_to_dict(info)
    payload["issues"] = []
    if info.validity == VALIDITY_INVALID_JSON:
        payload["issues"].append("备份文件不是合法 JSON")
    elif info.validity == VALIDITY_HAS_ORPHANS:
        payload["issues"].append(f"包含 {info.orphan_count} 条孤儿账单")
    if not info.is_valid_json and not info.has_project_uuid:
        payload["issues"].append("缺少 project_uuid")
    return payload


register(
    CommandSpec(
        name="backup.list",
        help="列出某项目的存档备份",
        handler=_backup_list,
        args=(
            ArgSpec(name="uuid", help="项目 UUID", kind="positional"),
            ArgSpec(name="valid_only", help="仅显示合法 JSON 的备份", type="flag"),
        ),
        examples=("cpa backup.list <uuid> --json",),
    )
)

register(
    CommandSpec(
        name="backup.inspect",
        help="检视单个备份文件的有效性与孤儿账单",
        handler=_backup_inspect,
        args=(ArgSpec(name="path", help="备份文件路径", kind="positional"),),
        examples=("cpa backup.inspect ./backups/p_xxx_20260101_120000.json --json",),
    )
)
