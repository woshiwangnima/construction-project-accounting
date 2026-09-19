"""Merge new configuration defaults without rewriting user preferences."""

from __future__ import annotations

import copy


def merge_named_rows(defaults: list, rows: list) -> list:
    """Fill fields by name while retaining user order and unknown rows.

    Missing rows are deliberately not reinserted: an empty list or a removed
    column can be a user preference. Lists without named defaults are replaced.
    """
    by_name = {
        row["name"]: row
        for row in defaults
        if isinstance(row, dict) and isinstance(row.get("name"), str)
    }
    result = []
    for row in rows:
        name = row.get("name") if isinstance(row, dict) else None
        if isinstance(name, str) and name in by_name:
            result.append(merge_defaults(by_name[name], row))
        else:
            result.append(copy.deepcopy(row))
    return result


def merge_defaults(defaults: dict, values: dict) -> dict:
    """Return independent configuration data, with explicit values winning.

    Dictionaries merge recursively. Named list entries inherit missing fields
    from the entry with the same name, including nested dictionaries/lists.
    Other lists (window sizes, release notes, etc.) retain replacement semantics.
    """
    result = copy.deepcopy(defaults)
    for key, value in values.items():
        base = defaults.get(key)
        if isinstance(base, dict) and isinstance(value, dict):
            result[key] = merge_defaults(base, value)
        elif isinstance(base, list) and isinstance(value, list):
            result[key] = merge_named_rows(base, value)
        else:
            result[key] = copy.deepcopy(value)
    return result
