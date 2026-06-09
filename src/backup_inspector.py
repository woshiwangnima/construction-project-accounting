"""存档检视模块：列表备份、孤儿检测、有效性报告。"""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Union

from .project_uuid import list_all_backup_files
from .billing_resolver import orphan_bills
from .billing import read_billing

VALIDITY_OK = "ok"
VALIDITY_HAS_ORPHANS = "orphans"
VALIDITY_INVALID_JSON = "invalid_json"


@dataclass
class BackupInfo:
    path: Path
    timestamp: str
    orphan_count: int
    is_valid_json: bool
    has_project_uuid: bool
    validity: str
    file_index: str = ""
    last_modified: str = ""
    status: str = ""
    trade_summary: str = "-"
    bill_summary: str = "-"


def _extract_timestamp(path: Path) -> str:
    """从 `p_{uuid}_{ts}.json` 文件名提取 ts。

    备份文件名格式：p_{uuid}_{YYYYMMDD}_{HHMMSS}.json
    时间戳由两段下划线分隔的数字组成，共 15 字符（含中间下划线）。
    """
    name = path.stem  # 去掉 .json
    # 从末尾抓 _{8 位日期}_{6 位时间}
    parts = name.rsplit("_", 2)
    if len(parts) == 3:
        date_part, time_part = parts[1], parts[2]
        if (len(date_part) == 8 and date_part.isdigit()
                and len(time_part) == 6 and time_part.isdigit()):
            return f"{date_part}_{time_part}"
    return name


def _extract_file_index(path: Path) -> str:
    parts = path.name.rsplit(".", 2)
    if len(parts) == 3 and parts[1].isdigit() and parts[2] == "json":
        return parts[1]
    return "-"


def orphan_count_from_backup(data: dict) -> int:
    """读取备份 JSON 中的 bills + trade_items 并计算孤儿数。

    使用 `billing_resolver.orphan_bills` 保持与项目其他地方一致。
    """
    bills = (data or {}).get("bills") or []
    if not bills:
        return 0
    trade_items = (data or {}).get("trade_items") or []
    return len(orphan_bills(bills, trade_items))


def summarize_trades(data: dict) -> str:
    items = (data or {}).get("trade_items") or []
    if not items:
        return "-"
    categories = (data or {}).get("category_order") or []
    cat_name_by_id = {c.get("id", ""): c.get("name", "") for c in categories if isinstance(c, dict)}
    counts: dict[str, dict[str, int]] = {}
    for item in items:
        cat = item.get("category") or cat_name_by_id.get(item.get("category_id", "")) or "未分类"
        bucket = counts.setdefault(cat, {"unit": 0, "no_unit": 0})
        billing = read_billing(item)
        if billing.has_unit:
            bucket["unit"] += 1
        else:
            bucket["no_unit"] += 1
    parts = []
    for cat, count in counts.items():
        total = count["unit"] + count["no_unit"]
        parts.append(f"{cat}：{total}项（有单价{count['unit']}，无单价{count['no_unit']}）")
    return "；".join(parts)


def summarize_bills(data: dict, orphan_count: int) -> str:
    bills = (data or {}).get("bills") or []
    total = len(bills)
    if orphan_count:
        return f"共 {total} 条（孤儿{orphan_count}）"
    return f"共 {total} 条"


def inspect_backup(path: Union[Path, str]) -> BackupInfo:
    """读取一个备份文件，返回有效性信息。"""
    path = Path(path)
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
    except (json.JSONDecodeError, OSError):
        return BackupInfo(
            path=path,
            timestamp=_extract_timestamp(path),
            orphan_count=0,
            is_valid_json=False,
            has_project_uuid=False,
            validity=VALIDITY_INVALID_JSON,
            file_index=_extract_file_index(path),
        )
    has_pu = bool(data.get("project_uuid"))
    oc = orphan_count_from_backup(data)
    validity = VALIDITY_OK if oc == 0 else VALIDITY_HAS_ORPHANS
    return BackupInfo(
        path=path,
        timestamp=_extract_timestamp(path),
        orphan_count=oc,
        is_valid_json=True,
        has_project_uuid=has_pu,
        validity=validity,
        file_index=_extract_file_index(path),
        last_modified=str(data.get("last_modified", "")),
        status=str(data.get("status", "")),
        trade_summary=summarize_trades(data),
        bill_summary=summarize_bills(data, oc),
    )


def list_backups_for(project_uuid: str) -> list[BackupInfo]:
    """列出某项目的所有备份，按时间倒序，每个附带有效性。"""
    paths = list_all_backup_files(project_uuid)
    return [inspect_backup(p) for p in paths]
