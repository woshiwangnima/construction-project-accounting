"""稳定 ID 生成。

设计
----
- category / trade item：创建时随机生成 12 字符 UUID（带 `cat_` / `ti_` 前缀），
  永不基于内容派生。改 name / 改 category 都不影响引用。
- bill：内容派生 SHA1（带 `b_` 前缀）。账单不参与跨实体引用，仅用于身份识别
  （编辑/粘贴/排序）。
"""
from __future__ import annotations

import hashlib
import uuid

ID_SEPARATOR = "|"


def generate_category_id() -> str:
    return "cat_" + uuid.uuid4().hex[:12]


def generate_trade_item_id() -> str:
    return "ti_" + uuid.uuid4().hex[:12]


def ensure_trade_item_id(item: dict) -> str:
    """Ensure a trade item has a non-empty ID and return it."""
    tid = str((item or {}).get("id") or "").strip()
    if not tid:
        tid = generate_trade_item_id()
        item["id"] = tid
    return tid


def compute_bill_id(trade_item_id: str, content: str, record_time: str) -> str:
    """账单自身稳定 id。

    - 空 trade_item_id 用 "orphan" 标识。
    - content + record_time 足以在同一项目内区分。
    """
    parts = [
        trade_item_id or "orphan",
        (content or "").strip(),
        (record_time or "").strip(),
    ]
    raw = ID_SEPARATOR.join(parts).encode("utf-8")
    return "b_" + hashlib.sha1(raw).hexdigest()[:12]
