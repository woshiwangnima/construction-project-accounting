"""Export settings data model with serialization/deserialization."""

from dataclasses import dataclass, field, asdict


@dataclass
class PriceListSettings:
    visible: bool = True
    show_no_unit_items: bool = False
    show_empty_categories: bool = False
    align_columns: bool = False
    name_width: int = 12
    price_width: int = 10


@dataclass
class TextColors:
    normal: str = "#000000"
    muted: str = "#888888"
    formula: str = "#2b6cb0"
    amount: str = "#c0392b"


@dataclass
class ExportDefaults:
    price_list_settings: PriceListSettings = field(default_factory=PriceListSettings)
    text_colors: TextColors = field(default_factory=TextColors)
    bg_color: str = "#ffffff"
    strip_category: bool = True
    show_project_date: bool = False
    show_record_time: bool = False
    show_export_time: bool = False
    append_note_to_item_title: bool = False

    def to_dict(self) -> dict:
        return {
            "price_list_settings": asdict(self.price_list_settings),
            "text_colors": asdict(self.text_colors),
            "export_bg_color": self.bg_color,
            "export_strip_category": self.strip_category,
            "export_show_project_date": self.show_project_date,
            "export_show_record_time": self.show_record_time,
            "export_show_export_time": self.show_export_time,
            "export_append_note_to_item_title": self.append_note_to_item_title,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "ExportDefaults":
        if not data:
            return cls()
        pl = data.get("price_list_settings", {})
        tc = data.get("text_colors", {})
        # 兼容旧字段名 show_per_incident_items → 新字段名 show_no_unit_items
        show_no_unit = pl.get(
            "show_no_unit_items",
            pl.get("show_per_incident_items", False),
        )
        return cls(
            price_list_settings=PriceListSettings(
                visible=pl.get("visible", True),
                show_no_unit_items=bool(show_no_unit),
                show_empty_categories=bool(pl.get("show_empty_categories", False)),
                align_columns=bool(pl.get("align_columns", False)),
                name_width=int(pl.get("name_width", 12) or 12),
                price_width=int(pl.get("price_width", 10) or 10),
            ),
            text_colors=TextColors(
                normal=tc.get("normal", "#000000"),
                muted=tc.get("muted", "#888888"),
                formula=tc.get("formula", "#2b6cb0"),
                amount=tc.get("amount", "#c0392b"),
            ),
            bg_color=data.get("export_bg_color", "#ffffff"),
            strip_category=data.get("export_strip_category", True),
            show_project_date=data.get("export_show_project_date", False),
            show_record_time=data.get("export_show_record_time", False),
            show_export_time=data.get("export_show_export_time", False),
            append_note_to_item_title=data.get("export_append_note_to_item_title", False),
        )
