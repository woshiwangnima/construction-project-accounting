from __future__ import annotations

from dataclasses import dataclass

from .billing import Billing


@dataclass
class TradeItem:
    id: str
    category_id: str
    name: str
    has_unit: bool = True
    unit_price: float = 1.0
    unit: str = ""
    category: str = ""

    @classmethod
    def from_dict(cls, d: dict) -> "TradeItem":
        billing = Billing.from_dict(d)
        return cls(
            id=d.get("id", ""),
            category_id=d.get("category_id", ""),
            name=d.get("name", ""),
            has_unit=billing.has_unit,
            unit_price=billing.unit_price,
            unit=billing.unit,
            category=d.get("category", ""),
        )

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "category_id": self.category_id,
            "name": self.name,
            "has_unit": self.has_unit,
            "unit_price": self.unit_price,
            "unit": self.unit,
        }

    def get(self, key: str, default=None):
        if key == "category":
            return self.category or default
        return getattr(self, key, default)

    def __getitem__(self, key: str):
        if key == "category":
            return self.category
        return getattr(self, key)

    def __setitem__(self, key: str, value) -> None:
        setattr(self, key, value)
