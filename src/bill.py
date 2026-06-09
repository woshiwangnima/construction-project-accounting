from __future__ import annotations

from dataclasses import dataclass


@dataclass
class Bill:
    id: str
    trade_item_id: str
    content: str
    note: str
    work_date_type: str
    work_date_start: str
    work_date_end: str
    record_time: str
    frozen_snapshot: dict | None = None
    frozen_total: float | None = None
    needs_attention: bool = False
    reviewed: bool = False

    @classmethod
    def from_dict(cls, d: dict) -> "Bill":
        return cls(
            id=d.get("id", ""),
            trade_item_id=d.get("trade_item_id", ""),
            content=d.get("content", ""),
            note=d.get("note", ""),
            work_date_type=d.get("work_date_type", "无时间"),
            work_date_start=d.get("work_date_start", "") or d.get("work_date", ""),
            work_date_end=d.get("work_date_end", ""),
            record_time=d.get("record_time", ""),
            frozen_snapshot=d.get("frozen_snapshot"),
            frozen_total=d.get("frozen_total"),
            needs_attention=d.get("needs_attention", False),
            reviewed=d.get("reviewed", False),
        )

    def to_dict(self) -> dict:
        d = {
            "id": self.id,
            "trade_item_id": self.trade_item_id,
            "content": self.content,
            "note": self.note,
            "work_date_type": self.work_date_type,
            "work_date_start": self.work_date_start,
            "work_date_end": self.work_date_end,
            "record_time": self.record_time,
        }
        if self.frozen_snapshot is not None:
            d["frozen_snapshot"] = self.frozen_snapshot
        if self.frozen_total is not None:
            d["frozen_total"] = self.frozen_total
        if self.needs_attention:
            d["needs_attention"] = True
        d["reviewed"] = bool(self.reviewed)
        return d

    def get(self, key: str, default=None):
        if key == "_needs_attention":
            return self.needs_attention
        if key == "reviewed":
            return self.reviewed
        return getattr(self, key, default)

    def __getitem__(self, key: str):
        if key == "_needs_attention":
            return self.needs_attention
        if key == "reviewed":
            return self.reviewed
        return getattr(self, key)

    def __contains__(self, key: str) -> bool:
        if key == "_needs_attention":
            return self.needs_attention
        if key in ("frozen_snapshot", "frozen_total"):
            return getattr(self, key) is not None
        if key == "needs_attention":
            return self.needs_attention
        if key == "reviewed":
            return True
        return hasattr(self, key)

    def __setitem__(self, key: str, value) -> None:
        if key == "_needs_attention":
            self.needs_attention = bool(value)
        elif key == "reviewed":
            self.reviewed = bool(value)
        else:
            setattr(self, key, value)

    def pop(self, key: str, default=None):
        if key in ("frozen_snapshot", "frozen_total"):
            value = getattr(self, key)
            setattr(self, key, None)
            return value
        if key in ("needs_attention", "_needs_attention"):
            value = self.needs_attention
            self.needs_attention = False
            return value
        if key == "reviewed":
            value = self.reviewed
            self.reviewed = False
            return value
        return default

    def clear(self) -> None:
        self.id = ""
        self.trade_item_id = ""
        self.content = ""
        self.note = ""
        self.work_date_type = "无时间"
        self.work_date_start = ""
        self.work_date_end = ""
        self.record_time = ""
        self.frozen_snapshot = None
        self.frozen_total = None
        self.needs_attention = False
        self.reviewed = False

    def update(self, data: dict) -> None:
        for key, value in data.items():
            self[key] = value
