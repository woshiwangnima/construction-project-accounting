"""应用内剪贴板：单槽结构，按 kind 区分账单 / 工作类型。

设计
----
- **单槽**：只保留最后一次复制的内容。多次复制互相覆盖。
- **跨项目持久**：实例由 ContentArea 持有，切换项目不丢失。重启 app 重置（不落盘）。
- **不依赖 Tk clipboard**：Tk clipboard 跨进程/重启/换窗口不可靠，
  也不能承载 trade_item_id 这类内部字段。
- **schema 校验**：set_* 时强制 payload 字段齐全 + kind 匹配。
"""
from __future__ import annotations

from typing import Any

# schema 版本：未来加字段时用 v2 + 兼容老 v1 解析
SCHEMA_VERSION = 1

# 类型标识
KIND_BILL = "bill"
KIND_TRADE_ITEM = "trade_item"


class ClipboardError(ValueError):
    """剪贴板 payload 不合法时抛。"""


# 必填字段：账单 payload
_REQUIRED_BILL_FIELDS = (
    "content",
    "trade_item_id",
    "trade_item_name_fallback",
)
# 必填字段：工作类型 payload
_REQUIRED_TRADE_ITEM_FIELDS = (
    "category",
    "name",
    "has_unit",
    "unit_price",
    "unit",
)


def _validate_bill_payload(payload: dict) -> None:
    missing = [k for k in _REQUIRED_BILL_FIELDS if k not in payload]
    if missing:
        raise ClipboardError(f"账单 payload 缺字段：{missing}")
    if not isinstance(payload["content"], str):
        raise ClipboardError("content 必须是 str")
    if not isinstance(payload["trade_item_id"], str):
        raise ClipboardError("trade_item_id 必须是 str")
    if not isinstance(payload["trade_item_name_fallback"], str):
        raise ClipboardError("trade_item_name_fallback 必须是 str")


def _validate_trade_item_payload(payload: dict) -> None:
    missing = [k for k in _REQUIRED_TRADE_ITEM_FIELDS if k not in payload]
    if missing:
        raise ClipboardError(f"工作类型 payload 缺字段：{missing}")
    if not isinstance(payload["category"], str):
        raise ClipboardError("category 必须是 str")
    if not isinstance(payload["name"], str):
        raise ClipboardError("name 必须是 str")
    if not isinstance(payload["has_unit"], bool):
        raise ClipboardError("has_unit 必须是 bool")
    try:
        float(payload["unit_price"])
    except (TypeError, ValueError):
        raise ClipboardError("unit_price 必须是数值")
    if not isinstance(payload["unit"], str):
        raise ClipboardError("unit 必须是 str")


class AppClipboard:
    """单槽应用剪贴板。"""

    def __init__(self) -> None:
        self._bill: dict | None = None
        self._trade_item: dict | None = None

    # ── 账单 ──

    def set_bill(self, payload: dict, source_ref: str = "") -> None:
        """存一条账单 payload。会覆盖旧的账单 + 旧的工作类型（不同 kind 互不覆盖）。"""
        _validate_bill_payload(payload)
        self._bill = {
            "kind": KIND_BILL,
            "schema_version": SCHEMA_VERSION,
            "source_project_ref": source_ref,
            "payload": _deepcopy_safe(payload),
        }
        # 复制账单 → 清掉旧的工作类型（用户语义上理解成「换内容」）
        self._trade_item = None

    def has_bill(self) -> bool:
        return self._bill is not None

    def get_bill(self) -> dict:
        if self._bill is None:
            raise ClipboardError("剪贴板里没有账单")
        return _deepcopy_safe(self._bill)

    # ── 工作类型 ──

    def set_trade_item(self, payload: dict, source_ref: str = "") -> None:
        _validate_trade_item_payload(payload)
        self._trade_item = {
            "kind": KIND_TRADE_ITEM,
            "schema_version": SCHEMA_VERSION,
            "source_project_ref": source_ref,
            "payload": _deepcopy_safe(payload),
        }
        self._bill = None

    def has_trade_item(self) -> bool:
        return self._trade_item is not None

    def get_trade_item(self) -> dict:
        if self._trade_item is None:
            raise ClipboardError("剪贴板里没有工作类型")
        return _deepcopy_safe(self._trade_item)

    # ── 通用 ──

    def clear(self) -> None:
        self._bill = None
        self._trade_item = None

    def summary(self) -> dict:
        """用于 UI 提示：返回当前各槽是否有内容。"""
        return {
            "has_bill": self.has_bill(),
            "has_trade_item": self.has_trade_item(),
        }


def _deepcopy_safe(obj: Any) -> Any:
    """不依赖 copy 模块：dict / list / 标量 浅克隆（够用了，payload 是 JSON 兼容结构）。"""
    if isinstance(obj, dict):
        return {k: _deepcopy_safe(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_deepcopy_safe(v) for v in obj]
    return obj
