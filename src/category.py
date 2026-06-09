from __future__ import annotations

from dataclasses import dataclass


@dataclass
class Category:
    id: str
    name: str

    @classmethod
    def from_dict(cls, d: dict) -> "Category":
        if isinstance(d, str):
            return cls(id="", name=d)
        return cls(id=d.get("id", ""), name=d.get("name", ""))

    def to_dict(self) -> dict:
        return {"id": self.id, "name": self.name}

    def __str__(self) -> str:
        return self.name

    def __eq__(self, other) -> bool:
        if isinstance(other, str):
            return self.name == other or self.id == other
        return super().__eq__(other)

    def get(self, key: str, default=None):
        return getattr(self, key, default)

    def __getitem__(self, key: str):
        return getattr(self, key)

    def __setitem__(self, key: str, value) -> None:
        setattr(self, key, value)
