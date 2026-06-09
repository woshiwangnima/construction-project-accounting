"""工作项目计价三件套（has_unit / unit_price / unit）。

抽象目的
--------
- 集中"按单价 / 无单价"语义的存取/校验/序列化逻辑
- 单一缺省源：`has_unit` 缺省 True；`unit_price` 缺省 1；`unit` 缺省 ""
- 编辑对话框、项目文件读写、`default_trade_items` 共用同一套 API

与 dict 存储的关系
------------------
磁盘上仍以 flat dict 形式存（key: `has_unit` / `unit_price` / `unit`），
保证向后兼容旧项目文件、旧 `app_config.json`。

`Billing` 是个值对象：
- `from_dict(d)` 容忍字段缺失（按缺省）
- `to_dict()` 永远输出完整三件套
- 写回 dict 时 `item.update(billing.to_dict())`

使用建议
--------
- 统一用 `read_billing(item)` 读取 → 得到 `Billing` 值对象。
- 写回用 `write_billing(item, billing)` 或 `Billing(...).to_dict()`。
- 磁盘格式仍是 flat dict，但所有调用方都不再直接 `.get("has_unit", ...)`。
"""
from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import Any


# 字段缺省值（业务约定；改这里就是改全应用缺省）
DEFAULT_HAS_UNIT = True
DEFAULT_UNIT_PRICE = 1.0
DEFAULT_UNIT = ""


@dataclass
class Billing:
    """工作项目计价三件套。"""

    has_unit: bool = DEFAULT_HAS_UNIT
    unit_price: float = DEFAULT_UNIT_PRICE
    unit: str = DEFAULT_UNIT

    def __post_init__(self):
        # 归一化：has_unit=False 时 unit/price 不应携带语义
        if not self.has_unit:
            self.unit_price = 0
            self.unit = ""
        # 类型兜底（JSON 加载后 int 会混入；避免下游 f-string 炸）
        self.has_unit = bool(self.has_unit)
        try:
            self.unit_price = float(self.unit_price)
        except (TypeError, ValueError):
            self.unit_price = DEFAULT_UNIT_PRICE
        self.unit = str(self.unit) if self.unit is not None else ""

    @property
    def is_per_unit(self) -> bool:
        return self.has_unit

    def to_dict(self) -> dict:
        """序列化为 dict（写回项目文件 / app_config.json）。"""
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict | None) -> "Billing":
        """反序列化：容忍字段缺失（按缺省），容忍类型错（强转）。"""
        if not d:
            return cls()
        return cls(
            has_unit=d.get("has_unit", DEFAULT_HAS_UNIT),
            unit_price=d.get("unit_price", DEFAULT_UNIT_PRICE),
            unit=d.get("unit", DEFAULT_UNIT),
        )

    def format_price(self) -> str:
        """展示用：'1.00 个' / '10.00 ¥/m²' / '无单价'。"""
        if not self.has_unit:
            return "无单价"
        return f"{self.unit_price:.2f} {self.unit}".strip()


def read_billing(item: dict) -> Billing:
    """从 item dict 读 Billing（缺字段不抛）。"""
    return Billing.from_dict(item)


def write_billing(item: dict, billing: Billing) -> None:
    """把 Billing 三件套写回 item dict（覆盖现有三键，保留其他键）。"""
    item["has_unit"] = billing.has_unit
    item["unit_price"] = billing.unit_price
    item["unit"] = billing.unit
