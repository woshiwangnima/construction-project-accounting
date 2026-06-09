def is_bill_reviewed(bill: dict) -> bool:
    return bool((bill or {}).get("reviewed", False))


def set_bill_reviewed(bill: dict, reviewed: bool) -> None:
    bill["reviewed"] = bool(reviewed)


def next_bulk_review_state(bills: list[dict]) -> bool:
    return not bills or not all(is_bill_reviewed(b) for b in bills)


def apply_bulk_review(bills: list[dict]) -> bool:
    reviewed = next_bulk_review_state(bills)
    for bill in bills:
        set_bill_reviewed(bill, reviewed)
    return reviewed


def copy_reviewed_state(source: dict | None, target: dict) -> None:
    if source is not None:
        target["reviewed"] = is_bill_reviewed(source)
