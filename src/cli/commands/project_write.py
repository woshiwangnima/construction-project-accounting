"""`project` 写入命令：创建、删除、改名、改状态。

并发安全：命令注册表持锁执行完整写入流程，
再调用 project_manager 的既有 API（内部自带 _project_write_lock 与备份策略），
绝不自行写 JSON 文件。
"""

from __future__ import annotations

import argparse

from ... import project_manager
from ...project_status import ProjectStatus
from ..common import project_summary, require_project
from ..errors import InvalidArgument
from ..registry import ArgSpec, CommandSpec, register

_STATUS_CHOICES = ("editing", "done")


def _parse_status(value: str) -> tuple[str, str]:
    """把用户输入的状态转成 (存储值, 显示名)。

    接受 editing/done，也接受界面上显示的 编辑中/已完成，
    以及历史值 active/completed，避免调用方猜。
    """
    raw = (value or "").strip()
    aliases = {
        "编辑中": "editing",
        "已完成": "done",
        "已结账": "done",
        "进行中": "editing",
        "active": "editing",
        "completed": "done",
    }
    resolved = aliases.get(raw, raw.lower())
    if resolved not in _STATUS_CHOICES:
        raise InvalidArgument(
            f"未知状态: {value}",
            details={"allowed": list(_STATUS_CHOICES), "aliases": list(aliases)},
        )
    return resolved, ProjectStatus.from_value(resolved).display_name


def _project_create(args: argparse.Namespace) -> dict:
    name = (args.name or "").strip()
    if not name:
        raise InvalidArgument("项目名称不能为空")
    status_value, _display = _parse_status(args.status or "editing")
    project = project_manager.create_project(
        name=name,
        status=status_value,
        description=args.description or "",
    )
    return project_summary(project)


def _project_delete(args: argparse.Namespace) -> dict:
    project = require_project(args.uuid)
    if not args.yes:
        raise InvalidArgument(
            f"删除项目「{project.name}」不可撤销（会先强制备份一次）。确认请加 --yes。",
            details={"uuid": project.project_uuid, "name": project.name},
        )
    removed = project_manager.delete_project(project.project_uuid)
    if not removed:
        raise InvalidArgument(
            f"删除失败: {project.project_uuid}", details={"uuid": project.project_uuid}
        )
    return {"uuid": project.project_uuid, "name": project.name, "deleted": True}


def _project_rename(args: argparse.Namespace) -> dict:
    project = require_project(args.uuid)
    name = (args.name or "").strip()
    if not name:
        raise InvalidArgument("项目名称不能为空")
    if name == project.name:
        return project_summary(project)

    # 走 update_project：内部加锁 + 备份 + 合并磁盘上的 is_pinned。
    updated = project
    updated.name = name
    project_manager.update_project(args.uuid, updated)
    return project_summary(require_project(args.uuid))


def _project_status(args: argparse.Namespace) -> dict:
    project = require_project(args.uuid)
    status_value, display = _parse_status(args.status)

    if project.status == status_value:
        result = project_summary(project)
        result["changed"] = False
        return result

    updated = project
    updated.status = status_value
    project_manager.update_project(args.uuid, updated)

    refreshed = require_project(args.uuid)
    result = project_summary(refreshed)
    result["status_display"] = display
    result["changed"] = True
    return result


def _project_set_description(args: argparse.Namespace) -> dict:
    project = require_project(args.uuid)
    updated = project
    updated.description = args.description or ""
    project_manager.update_project(args.uuid, updated)
    result = project_summary(require_project(args.uuid))
    result["description"] = updated.description
    return result


register(
    CommandSpec(
        name="project.create",
        help="创建新项目",
        handler=_project_create,
        read_only=False,
        args=(
            ArgSpec(name="name", help="项目名称", kind="positional"),
            ArgSpec(
                name="status",
                help="初始状态：editing(编辑中)/done(已完成)",
                choices=_STATUS_CHOICES,
                default="editing",
            ),
            ArgSpec(name="description", help="项目备注"),
        ),
        examples=("cpa project.create 某某小区 --json",),
    )
)

register(
    CommandSpec(
        name="project.delete",
        help="删除项目（会先强制备份一次；需 --yes 确认）",
        handler=_project_delete,
        read_only=False,
        args=(
            ArgSpec(name="uuid", help="项目 UUID", kind="positional"),
            ArgSpec(name="yes", help="确认删除", type="flag"),
        ),
        examples=("cpa project.delete <uuid> --yes --json",),
    )
)

register(
    CommandSpec(
        name="project.rename",
        help="重命名项目",
        handler=_project_rename,
        read_only=False,
        args=(
            ArgSpec(name="uuid", help="项目 UUID", kind="positional"),
            ArgSpec(name="name", help="新名称", kind="positional"),
        ),
        examples=("cpa project.rename <uuid> 新名称 --json",),
    )
)

register(
    CommandSpec(
        name="project.status",
        help="修改项目状态（editing/done，也接受 编辑中/已完成）",
        handler=_project_status,
        read_only=False,
        args=(
            ArgSpec(name="uuid", help="项目 UUID", kind="positional"),
            ArgSpec(name="status", help="新状态", kind="positional"),
        ),
        examples=("cpa project.status <uuid> done --json",),
    )
)

register(
    CommandSpec(
        name="project.set-description",
        help="设置项目备注",
        handler=_project_set_description,
        read_only=False,
        args=(
            ArgSpec(name="uuid", help="项目 UUID", kind="positional"),
            ArgSpec(name="description", help="备注内容", kind="positional"),
        ),
        examples=("cpa project.set-description <uuid> 备注 --json",),
    )
)
