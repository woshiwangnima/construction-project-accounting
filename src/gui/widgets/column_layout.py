from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ColumnSpec:
    key: str
    min_width: int = 8
    content_min_width: int = 0
    resizable: bool = True

    @property
    def effective_min_width(self) -> int:
        return max(int(self.min_width), int(self.content_min_width), 1)


def _positive_weights(columns: list[ColumnSpec], weights: dict[str, float]) -> dict[str, float]:
    result: dict[str, float] = {}
    for col in columns:
        try:
            value = float(weights.get(col.key, 0))
        except (TypeError, ValueError):
            value = 0
        if value > 0:
            result[col.key] = value
    if result:
        return result
    return {col.key: 1.0 for col in columns}


def compute_column_pixels(columns: list[ColumnSpec], weights: dict[str, float], total_width: int) -> dict[str, int]:
    if not columns or total_width < 1:
        return {}
    mins = {col.key: col.effective_min_width for col in columns}
    min_total = sum(mins.values())
    if total_width <= min_total:
        return mins

    valid_weights = _positive_weights(columns, weights)
    weight_sum = sum(valid_weights.values())
    pixels: dict[str, int] = {}
    allocated = 0
    for col in columns[:-1]:
        width = int(round(total_width * valid_weights.get(col.key, 0.0) / weight_sum))
        pixels[col.key] = max(mins[col.key], width)
        allocated += pixels[col.key]
    last = columns[-1]
    pixels[last.key] = max(mins[last.key], total_width - allocated)

    overflow = sum(pixels.values()) - total_width
    if overflow > 0:
        for col in reversed(columns):
            reducible = max(0, pixels[col.key] - mins[col.key])
            take = min(reducible, overflow)
            pixels[col.key] -= take
            overflow -= take
            if overflow <= 0:
                break
    return pixels


def capture_column_weights(columns: list[ColumnSpec], pixels: dict[str, int]) -> dict[str, float]:
    measured: dict[str, int] = {}
    for col in columns:
        if not col.resizable:
            continue
        try:
            width = int(pixels.get(col.key, 0))
        except (TypeError, ValueError):
            width = 0
        measured[col.key] = max(width, col.effective_min_width)
    total = sum(measured.values())
    if total <= 0:
        return {}
    return {key: round(width / total, 10) for key, width in measured.items()}


def resize_adjacent_columns(columns: list[ColumnSpec], pixels: dict[str, int],
                            left_key: str, right_key: str, delta: int) -> dict[str, int]:
    specs = {col.key: col for col in columns}
    if left_key not in specs or right_key not in specs:
        return dict(pixels)
    left = int(pixels.get(left_key, 0))
    right = int(pixels.get(right_key, 0))
    total = left + right
    left_min = specs[left_key].effective_min_width
    right_min = specs[right_key].effective_min_width
    if total <= left_min + right_min:
        return dict(pixels)

    wanted_left = left + int(delta)
    wanted_left = max(left_min, min(wanted_left, total - right_min))
    result = dict(pixels)
    result[left_key] = wanted_left
    result[right_key] = total - wanted_left
    return result
