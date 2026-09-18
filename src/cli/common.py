"""CLI 共用的序列化与配置读取助手。

原则：CLI 不做任何业务计算，只把 domain 层的结果转成可序列化结构。
公式求值、合计重算、孤儿判定一律调用现有模块，保证与 GUI 结果一致。
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from .. import project_manager
from ..config_loader import load_app
from ..project import Project
from ..symbol_mapping import DEFAULT_SYMBOL_MAPPING, normalize_symbol_mapping
from .errors import ProjectNotFound


def op_map() -> dict:
    """取与 GUI 同源的运算符映射（来自 app_config 的 symbol_mapping）。

    不能在此写死 × → * 之类的映射：用户改过符号配置后，CLI 与 GUI
    的算式结果必须仍然一致。
    """
    try:
        raw = load_app().get("symbol_mapping")
    except Exception:
        raw = None
    return normalize_symbol_mapping(raw or DEFAULT_SYMBOL_MAPPING)


def require_project(uuid: str) -> Project:
    """按 UUID 取项目，任何失败都转成 ProjectNotFound。

    project_manager.get_project 对格式非法的 UUID 会先抛 ValueError（在返回
    None 之前），调用方不应感知这个区分——对它们而言都是"没有这个项目"。
    """
    try:
        project = project_manager.get_project(uuid)
    except ValueError as exc:
        raise ProjectNotFound(
            f"项目 UUID 格式非法: {uuid}", details={"uuid": uuid, "reason": str(exc)}
        ) from exc
    if project is None:
        raise ProjectNotFound(f"项目不存在: {uuid}", details={"uuid": uuid})
    return project


def project_summary(project: Project) -> dict:
    """项目列表用的精简结构（不含账单明细，避免列表输出过大）。"""
    return {
        "uuid": project.project_uuid,
        "name": project.name,
        "status": project.status,
        "created_at": project.created_at,
        "last_modified": project.last_modified,
        "description": project.description,
        "is_pinned": bool(project.is_pinned),
        "schema_version": project.schema_version,
        "bill_count": len(project.bills),
        "trade_item_count": len(project.trade_items),
    }


def project_detail(project: Project) -> dict:
    """完整项目结构（含账单与工种），字段名沿用 to_dict 的磁盘格式。"""
    data = project.to_dict()
    return _jsonable(data)


def _jsonable(value: Any) -> Any:
    """兜底：把 Path / Decimal 等非 JSON 原生类型转成字符串。"""
    if isinstance(value, dict):
        return {str(k): _jsonable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(v) for v in value]
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return str(value)


def projects_dir() -> Path:
    return Path(os.environ.get("CPA_PROJECTS_DIR") or project_manager.PROJECTS_DIR)


def backups_dir() -> Path:
    return Path(os.environ.get("CPA_BACKUPS_DIR") or project_manager.BACKUPS_DIR)
