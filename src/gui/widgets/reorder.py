from __future__ import annotations

from collections.abc import Callable, Sequence
from typing import TypeVar


T = TypeVar("T")


def move_item(items: Sequence[T], from_idx: int, to_idx: int) -> list[T]:
    result = list(items)
    if from_idx < 0 or from_idx >= len(result):
        return result
    to_idx = max(0, min(to_idx, len(result)))
    if from_idx == to_idx:
        return result
    item = result.pop(from_idx)
    if to_idx > from_idx:
        to_idx -= 1
    result.insert(to_idx, item)
    return result


def reorder_subset_by_ids(
    all_items: Sequence[T],
    visible_ids: Sequence[str],
    from_idx: int,
    to_idx: int,
    id_getter: Callable[[T], str],
) -> list[T]:
    visible_ids = list(visible_ids)
    reordered_ids = move_item(visible_ids, from_idx, to_idx)
    id_to_item = {id_getter(item): item for item in all_items}
    replacement_iter = iter(id_to_item[item_id] for item_id in reordered_ids if item_id in id_to_item)
    visible_set = set(visible_ids)
    result: list[T] = []
    for item in all_items:
        if id_getter(item) in visible_set:
            result.append(next(replacement_iter))
        else:
            result.append(item)
    return result
