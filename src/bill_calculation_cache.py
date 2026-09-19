"""Reuse bill calculations until their formula or billing inputs change."""
from __future__ import annotations

from copy import deepcopy
from dataclasses import replace

from .bill_recompute import calculate_bill
from .billing_resolver import build_trade_item_index
from .money import sum_money


def _billing_inputs(item):
    if not item:
        return None
    return tuple(item.get(key) for key in (
        "category", "name", "has_unit", "unit_price", "unit",
    ))


class BillCalculationCache:
    """A render-local cache bounded to the current bill list.

    Keys contain copied scalar values, so in-place edits to a bill, a trade
    item, a frozen snapshot, or the operator mapping invalidate correctly.
    Display-only changes (review, notes, dates) do not evaluate formulas again.
    """

    def __init__(self):
        self._entries = {}
        self._op_map = None

    def clear(self) -> None:
        self._entries.clear()
        self._op_map = None

    def prepare(self, bills, trade_items, op_map):
        mapping = deepcopy(op_map or {})
        if mapping != self._op_map:
            self._entries.clear()
            self._op_map = mapping
        items = trade_items or []
        index = build_trade_item_index(items)
        trade_inputs = {key: _billing_inputs(item) for key, item in index.items()}
        entries = {}
        calculations = []
        for bill in bills or []:
            item_id = bill.get("trade_item_id", "")
            item = index.get(str(item_id)) if item_id else None
            snapshot = bill.get("frozen_snapshot") or {}
            signature = (
                bill.get("content", ""), item_id,
                trade_inputs.get(str(item_id)) if item is not None else None,
                _billing_inputs(snapshot) if isinstance(snapshot, dict) else None,
                bill.get("frozen_total"),
            )
            key = id(bill)
            previous = self._entries.get(key)
            if previous is not None and previous[0] is bill and previous[1] == signature:
                calculation = previous[2]
                if calculation.trade_item is not item:
                    calculation = replace(calculation, trade_item=item)
            else:
                calculation = calculate_bill(bill, items, mapping, index)
            entries[key] = (bill, signature, calculation)
            calculations.append(calculation)
        self._entries = entries
        return calculations

    def summarize(self, bills, trade_items, op_map):
        calculations = self.prepare(bills, trade_items, op_map)
        return (
            calculations,
            sum_money(item.total for item in calculations),
            sum(item.formula_error for item in calculations),
        )
