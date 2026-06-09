"""项目状态枚举。

取代旧的 "进行中"/"已结账" 字符串，引入 "编辑中"/"已完成" 语义。
- EDITING（编辑中）：项目数据可被修改；用绿色显示
- DONE（已完成）：项目数据冻结；只能"生成图片"和"更改列宽"；用灰色显示

为了向后兼容磁盘上可能存在的旧值（"active" / "completed"），`from_value` 接受旧值并映射到新枚举。
"""
from __future__ import annotations

from enum import Enum


class ProjectStatus(str, Enum):
    EDITING = "editing"
    DONE = "done"

    @classmethod
    def from_value(cls, value) -> "ProjectStatus":
        """接受枚举、新字符串 ("editing"/"done") 或旧字符串 ("active"/"completed")。"""
        if isinstance(value, ProjectStatus):
            return value
        if value == "active":
            return cls.EDITING
        if value == "completed":
            return cls.DONE
        if isinstance(value, str):
            try:
                return cls(value)
            except ValueError:
                pass
        return cls.EDITING

    @property
    def display_name(self) -> str:
        return "编辑中" if self == ProjectStatus.EDITING else "已完成"

    @property
    def color(self) -> str:
        # 绿/灰
        return "#38a169" if self == ProjectStatus.EDITING else "#a0aec0"

    @property
    def icon(self) -> str:
        return "●" if self == ProjectStatus.EDITING else "○"

    @property
    def is_editable(self) -> bool:
        return self == ProjectStatus.EDITING

    def __str__(self) -> str:
        return self.value
