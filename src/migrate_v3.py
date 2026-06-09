"""一次性迁移脚本：旧版项目 JSON → 新版 dataclass 格式。

运行：
    python -m src.migrate_v3 --projects-dir ./projects --backups-dir ./backups
    python -m src.migrate_v3 --dry-run
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import sys
import time
import uuid
from datetime import datetime
from pathlib import Path

PROJECTS_DIR = os.environ.get("CPA_PROJECTS_DIR", "./projects")
BACKUPS_DIR = os.environ.get("CPA_BACKUPS_DIR", "./backups")


def _atomic_write(path: str, data: dict) -> None:
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, path)


def _backup(src_path: str, project_uuid: str) -> None:
    os.makedirs(BACKUPS_DIR, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    dst = os.path.join(BACKUPS_DIR, f"p_{project_uuid}_{ts}.json")
    shutil.copy2(src_path, dst)


def _gen_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:12]}"


def _gen_bill_id(trade_item_id: str, content: str, record_time: str) -> str:
    parts = [trade_item_id or "orphan", (content or "").strip(), (record_time or "").strip()]
    raw = "|".join(parts).encode("utf-8")
    return "b_" + hashlib.sha1(raw).hexdigest()[:12]


def _migrate_one(file_path: str, dry_run: bool) -> dict:
    """迁移单个项目文件。返回报告 dict。"""
    report = {"path": file_path, "status": "ok", "categories": 0, "trade_items": 0, "bills": 0, "orphans": 0}

    with open(file_path, encoding="utf-8") as f:
        data = json.load(f)

    old_co = data.get("category_order", [])
    cat_id_by_name: dict[str, str] = {}
    cat_name_by_old_id: dict[str, str] = {}
    new_co: list[dict] = []
    if old_co and isinstance(old_co[0], str):
        for name in old_co:
            if name not in cat_id_by_name:
                cat_id_by_name[name] = _gen_id("cat")
            new_co.append({"id": cat_id_by_name[name], "name": name})
        report["categories"] = len(new_co)
    elif old_co and isinstance(old_co[0], dict):
        new_co = []
        for c in old_co:
            cid = c.get("id") or _gen_id("cat")
            name = c.get("name", "")
            new_co.append({"id": cid, "name": name})
            cat_id_by_name[name] = cid
            if c.get("id"):
                cat_name_by_old_id[c.get("id")] = name
        report["categories"] = len(new_co)
    data["category_order"] = new_co

    old_ti = data.get("trade_items", [])
    old_ti_id_to_new: dict[str, str] = {}
    new_ti: list[dict] = []
    for it in old_ti:
        old_id = it.get("id", "")
        is_v3_ti = bool(it.get("category_id")) and "category" not in it
        new_id = old_id if is_v3_ti and old_id else _gen_id("ti")
        old_ti_id_to_new[old_id] = new_id
        category_name = it.get("category", "")
        category_id = it.get("category_id", "")
        if category_id and not category_name:
            category_name = cat_name_by_old_id.get(category_id, "")
        new_ti.append({
            "id": new_id,
            "category_id": category_id or cat_id_by_name.get(category_name, ""),
            "name": it.get("name", ""),
            "has_unit": bool(it.get("has_unit", True)),
            "unit_price": float(it.get("unit_price", 1.0)),
            "unit": str(it.get("unit", "")),
        })
    data["trade_items"] = new_ti
    report["trade_items"] = len(new_ti)
    valid_new_ti_ids = {it["id"] for it in new_ti if it.get("id")}

    old_bills = data.get("bills", [])
    new_bills: list[dict] = []
    for b in old_bills:
        old_ti_id = b.get("trade_item_id", "")
        if old_ti_id in old_ti_id_to_new:
            new_ti_id = old_ti_id_to_new[old_ti_id]
        elif old_ti_id in valid_new_ti_ids:
            new_ti_id = old_ti_id
        else:
            new_ti_id = ""
        is_orphan = not new_ti_id
        if is_orphan:
            report["orphans"] += 1

        new_bill: dict = {
            "trade_item_id": new_ti_id,
            "content": b.get("content", ""),
            "note": b.get("note", ""),
            "work_date_type": b.get("work_date_type", "无时间"),
            "work_date_start": b.get("work_date_start", "") or b.get("work_date", ""),
            "work_date_end": b.get("work_date_end", ""),
            "record_time": b.get("record_time", ""),
        }
        if b.get("frozen_snapshot") is not None:
            new_bill["frozen_snapshot"] = b["frozen_snapshot"]
        if b.get("frozen_total") is not None:
            new_bill["frozen_total"] = b["frozen_total"]
        if b.get("needs_attention") or b.get("_needs_attention"):
            new_bill["needs_attention"] = True
        if is_orphan and b.get("frozen_snapshot") is not None:
            new_bill["needs_attention"] = True
        new_bill["id"] = _gen_bill_id(new_ti_id, new_bill["content"], new_bill["record_time"])
        new_bills.append(new_bill)
    data["bills"] = new_bills
    report["bills"] = len(new_bills)

    data.pop("_migrated_v2", None)
    data.pop("_migrated_v3", None)
    data.pop("_path", None)
    data.pop("_needs_attention", None)

    if not dry_run:
        uuid_part = data.get("project_uuid", Path(file_path).stem)
        _backup(file_path, uuid_part)
        _atomic_write(file_path, data)

    return report


def main() -> int:
    parser = argparse.ArgumentParser(description="迁移旧版项目 JSON 到 v3 格式")
    parser.add_argument("--projects-dir", default=PROJECTS_DIR)
    parser.add_argument("--backups-dir", default=BACKUPS_DIR)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    projects_dir = args.projects_dir
    if not os.path.isdir(projects_dir):
        print(f"项目目录不存在: {projects_dir}", file=sys.stderr)
        return 1

    if not args.dry_run:
        print(f"将迁移 {projects_dir} 下的项目，备份到 {args.backups_dir}（Ctrl-C 中止）")
        print("3 秒后开始...")
        time.sleep(3)

    files = [os.path.join(projects_dir, f)
             for f in os.listdir(projects_dir)
             if f.endswith(".json")]
    total = len(files)
    ok = 0
    fail = 0
    total_orphans = 0
    for fp in files:
        try:
            r = _migrate_one(fp, args.dry_run)
            ok += 1
            total_orphans += r["orphans"]
            print(f"  PASS  {os.path.basename(fp)}: {r['categories']} 分类, {r['trade_items']} 工作项, {r['bills']} 账单, {r['orphans']} 孤儿")
        except Exception as e:
            fail += 1
            print(f"  FAIL  {os.path.basename(fp)}: {e}", file=sys.stderr)

    mode = "[DRY-RUN] " if args.dry_run else ""
    print(f"\n{mode}完成：成功 {ok} / 失败 {fail} / 总孤儿账单 {total_orphans}")
    return 0 if fail == 0 else 2


if __name__ == "__main__":
    sys.exit(main())
