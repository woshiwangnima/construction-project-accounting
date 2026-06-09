from __future__ import annotations

from dataclasses import dataclass, field

from .bill import Bill
from .category import Category
from .project_status import ProjectStatus
from .trade_item_id import ensure_trade_item_id, generate_category_id
from .trade_item import TradeItem
from .versioning import APP_VERSION, CURRENT_SCHEMA_VERSION, schema_version_of


@dataclass
class Project:
    project_uuid: str
    name: str
    status: str
    created_at: str
    last_modified: str
    description: str
    project_date_type: str
    project_date_start: str
    project_date_end: str
    category_order: list[Category] = field(default_factory=list)
    trade_items: list[TradeItem] = field(default_factory=list)
    bills: list[Bill] = field(default_factory=list)
    bill_column_widths: dict = field(default_factory=dict)
    worker_column_widths: dict = field(default_factory=dict)
    view_state: dict = field(default_factory=dict)
    app_version: str = APP_VERSION
    schema_version: int = CURRENT_SCHEMA_VERSION

    @classmethod
    def from_dict(cls, d: dict) -> "Project":
        categories = [Category.from_dict(c) for c in d.get("category_order", [])]
        for category in categories:
            if not category.id:
                category.id = generate_category_id()
        cat_name_by_id = {c.id: c.name for c in categories}
        trade_items = [TradeItem.from_dict(t) for t in d.get("trade_items", [])]
        unknown_id_to_name: dict[str, str] = {}
        next_category_idx = 0
        for item in trade_items:
            if not item.category and item.category_id:
                item.category = cat_name_by_id.get(item.category_id, "")
                if not item.category and categories:
                    if item.category_id not in unknown_id_to_name:
                        if next_category_idx < len(categories):
                            unknown_id_to_name[item.category_id] = categories[next_category_idx].name
                            next_category_idx += 1
                    item.category = unknown_id_to_name.get(item.category_id, "")
        return cls(
            project_uuid=d.get("project_uuid", ""),
            name=d.get("name", ""),
            status=ProjectStatus.from_value(d.get("status", ProjectStatus.EDITING.value)).value,
            created_at=d.get("created_at", ""),
            last_modified=d.get("last_modified", ""),
            description=d.get("description", ""),
            project_date_type=d.get("project_date_type", "无时间"),
            project_date_start=d.get("project_date_start", ""),
            project_date_end=d.get("project_date_end", ""),
            category_order=categories,
            trade_items=trade_items,
            bills=[Bill.from_dict(b) for b in d.get("bills", [])],
            bill_column_widths=dict(d.get("bill_column_widths", {})),
            worker_column_widths=dict(d.get("worker_column_widths", {})),
            view_state=dict(d.get("view_state", {})),
            app_version=str(d.get("app_version", APP_VERSION)),
            schema_version=schema_version_of(d),
        )

    def to_dict(self) -> dict:
        self.category_order = self._coerce_category_order(self.category_order)
        self._ensure_categories_for_trade_items()
        self._sync_trade_item_category_ids()
        return {
            "app_version": APP_VERSION,
            "schema_version": CURRENT_SCHEMA_VERSION,
            "project_uuid": self.project_uuid,
            "name": self.name,
            "status": self.status,
            "created_at": self.created_at,
            "last_modified": self.last_modified,
            "description": self.description,
            "project_date_type": self.project_date_type,
            "project_date_start": self.project_date_start,
            "project_date_end": self.project_date_end,
            "category_order": [c.to_dict() for c in self.category_order],
            "trade_items": [self._trade_item_to_dict(t) for t in self.trade_items],
            "bills": [b.to_dict() if hasattr(b, "to_dict") else dict(b) for b in self.bills],
            "bill_column_widths": dict(self.bill_column_widths),
            "worker_column_widths": dict(self.worker_column_widths),
            "view_state": dict(self.view_state),
        }

    def _category_names(self) -> list[str]:
        return [c.name if isinstance(c, Category) else str(c) for c in self.category_order]

    def _category_id_by_name(self) -> dict[str, str]:
        return {c.name: c.id for c in self.category_order if isinstance(c, Category)}

    def _ensure_categories_for_trade_items(self) -> None:
        names = set(self._category_names())
        for item in self.trade_items:
            category = item.get("category", "") if hasattr(item, "get") else ""
            if category and category not in names:
                self.category_order.append(Category(id=generate_category_id(), name=category))
                names.add(category)

    def _trade_item_to_dict(self, item) -> dict:
        if isinstance(item, TradeItem):
            if not item.id:
                item.id = ensure_trade_item_id({})
            if item.category and not item.category_id:
                item.category_id = self._category_id_by_name().get(item.category, "")
            return item.to_dict()
        d = dict(item)
        ensure_trade_item_id(d)
        category = d.get("category", "")
        if category and not d.get("category_id"):
            d["category_id"] = self._category_id_by_name().get(category, "")
        return TradeItem.from_dict(d).to_dict()

    def _coerce_category_order(self, value) -> list[Category]:
        existing = self._category_id_by_name()
        result: list[Category] = []
        for item in value or []:
            if isinstance(item, Category):
                result.append(item)
            elif isinstance(item, dict):
                result.append(Category.from_dict(item))
            else:
                name = str(item)
                result.append(Category(id=existing.get(name) or generate_category_id(), name=name))
        return result

    def get(self, key: str, default=None):
        if key == "_path":
            return self.project_uuid
        if key == "category_order":
            return self._category_names()
        return getattr(self, key, default)

    def __getitem__(self, key: str):
        value = self.get(key)
        if value is None and not hasattr(self, key) and key != "_path":
            raise KeyError(key)
        return value

    def __contains__(self, key: str) -> bool:
        return key == "_path" or hasattr(self, key)

    def __setitem__(self, key: str, value) -> None:
        if key == "category_order":
            self.category_order = self._coerce_category_order(value)
            self._sync_trade_item_category_ids()
            return
        if key == "trade_items":
            self.trade_items = [t if isinstance(t, TradeItem) else TradeItem.from_dict(t) for t in value]
            self._sync_trade_item_category_ids()
            return
        if key == "bills":
            self.bills = [b if isinstance(b, Bill) else Bill.from_dict(b) for b in value]
            return
        setattr(self, key, value)

    def setdefault(self, key: str, default):
        current = self.get(key)
        if current is None:
            self[key] = default
            return self.get(key)
        return current

    def _sync_trade_item_category_ids(self) -> None:
        ids = self._category_id_by_name()
        names = {c.id: c.name for c in self.category_order if isinstance(c, Category)}
        for item in self.trade_items:
            if isinstance(item, TradeItem):
                if item.category_id in names:
                    item.category = names[item.category_id]
                if item.category:
                    item.category_id = ids.get(item.category, "")
            elif item.get("category"):
                item["category_id"] = ids.get(item.get("category"), "")
            elif item.get("category_id") in names:
                item["category"] = names[item.get("category_id")]
