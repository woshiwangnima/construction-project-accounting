from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ScrollAnchor:
    item_id: str
    offset_px: int = 0
    offset_ratio: float = 0.0
    fallback_index: int = 0
    viewport_height: int = 0
    content_height: int = 0

    def to_dict(self) -> dict:
        return {
            "item_id": self.item_id,
            "offset_px": self.offset_px,
            "offset_ratio": self.offset_ratio,
            "fallback_index": self.fallback_index,
            "viewport_height": self.viewport_height,
            "content_height": self.content_height,
        }

    @classmethod
    def from_dict(cls, data: dict | None) -> "ScrollAnchor | None":
        if not isinstance(data, dict) or not data.get("item_id"):
            return None
        return cls(
            item_id=str(data.get("item_id", "")),
            offset_px=int(data.get("offset_px", 0) or 0),
            offset_ratio=float(data.get("offset_ratio", 0.0) or 0.0),
            fallback_index=int(data.get("fallback_index", 0) or 0),
            viewport_height=int(data.get("viewport_height", 0) or 0),
            content_height=int(data.get("content_height", 0) or 0),
        )


@dataclass(frozen=True)
class RowGeometry:
    item_id: str
    top: int
    height: int


def geometry_signature(rows: list[RowGeometry], viewport_height: int, content_height: int) -> tuple:
    return (
        int(viewport_height),
        int(content_height),
        tuple((row.item_id, int(row.top), int(row.height)) for row in rows),
    )


def is_geometry_stable(previous_signature, current_signature) -> bool:
    return previous_signature is not None and previous_signature == current_signature


def capture_anchor_from_geometry(rows: list[RowGeometry], top_y: int,
                                 viewport_height: int, content_height: int) -> ScrollAnchor | None:
    if not rows:
        return None
    idx = top_index_from_rows([r.top for r in rows], [r.height for r in rows], top_y)
    if idx is None:
        return None
    row = rows[idx]
    offset_px = max(0, int(top_y - row.top))
    return ScrollAnchor(
        item_id=row.item_id,
        offset_px=offset_px,
        offset_ratio=relative_offset_in_row(row.top, row.height, top_y),
        fallback_index=idx,
        viewport_height=viewport_height,
        content_height=content_height,
    )


def restore_y_from_anchor(anchor: ScrollAnchor | dict | None, rows: list[RowGeometry],
                          viewport_height: int, content_height: int) -> int:
    if isinstance(anchor, dict):
        anchor = ScrollAnchor.from_dict(anchor)
    if anchor is None or not rows:
        return 0

    row_index = next((idx for idx, row in enumerate(rows) if row.item_id == anchor.item_id), None)
    if row_index is None:
        row_index = max(0, min(anchor.fallback_index, len(rows) - 1))
    row = rows[row_index]
    return restore_top_y(
        row_top=row.top,
        row_height=row.height,
        offset_ratio=anchor.offset_ratio,
        content_height=content_height,
        viewport_height=viewport_height,
    )


def top_index_from_rows(row_tops: list[int], row_heights: list[int], top_y: int) -> int | None:
    if not row_tops or not row_heights:
        return None
    for idx, row_top in enumerate(row_tops):
        row_bottom = row_top + max(row_heights[idx], 1)
        if row_bottom > top_y:
            return idx
    return len(row_tops) - 1


def relative_offset_in_row(row_top: int, row_height: int, top_y: int) -> float:
    row_height = max(row_height, 1)
    return max(0.0, min(1.0, (top_y - row_top) / row_height))


def restore_top_y(row_top: int, row_height: int, offset_ratio: float,
                  content_height: int, viewport_height: int) -> int:
    wanted = row_top + int(max(row_height, 1) * max(0.0, min(1.0, offset_ratio)))
    max_top = max(0, content_height - max(viewport_height, 1))
    return max(0, min(wanted, max_top))
