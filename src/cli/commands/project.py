"""`project` 命令组：列表、详情、导出、导入。"""

from __future__ import annotations

import argparse
from pathlib import Path

from ... import project_manager
from ..common import project_detail, project_summary, require_project
from ..errors import ExportFailed, InvalidArgument
from ..registry import ArgSpec, CommandSpec, register


def _project_list(args: argparse.Namespace) -> dict:
    projects = project_manager.list_projects()
    if getattr(args, "status", None):
        projects = [p for p in projects if p.status == args.status]
    if getattr(args, "name_contains", None):
        needle = args.name_contains
        projects = [p for p in projects if needle in (p.name or "")]
    summaries = [project_summary(p) for p in projects]
    return {"count": len(summaries), "projects": summaries}


def _project_show(args: argparse.Namespace) -> dict:
    project = require_project(args.uuid)
    if args.summary_only:
        return project_summary(project)
    return project_detail(project)


def _project_export(args: argparse.Namespace) -> dict:
    project = require_project(args.uuid)
    output = Path(args.output).expanduser()
    if output.is_dir():
        output = output / f"{project.project_uuid}.json"
    try:
        output.parent.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        raise ExportFailed(
            f"无法创建输出目录: {output.parent}", details={"reason": str(exc)}
        ) from exc

    if output.exists() and not args.overwrite:
        raise ExportFailed(
            f"目标文件已存在: {output}（如需覆盖请加 --overwrite）",
            details={"path": str(output)},
        )

    # 复用 project_manager.export_project：内部走原子写入，不自己 dump JSON
    success = project_manager.export_project(project.project_uuid, str(output))
    if not success:
        raise ExportFailed(f"导出失败: {output}", details={"path": str(output)})
    return {
        "uuid": project.project_uuid,
        "name": project.name,
        "output": str(output),
        "size": output.stat().st_size if output.exists() else 0,
    }


def _project_import(args: argparse.Namespace) -> dict:
    source = Path(args.input).expanduser()
    if not source.is_file():
        raise InvalidArgument(
            f"导入文件不存在: {source}", details={"path": str(source)}
        )
    project = project_manager.import_project(str(source))
    if project is None:
        raise InvalidArgument(
            f"导入失败，文件不是合法的项目文件: {source}",
            details={"path": str(source)},
        )
    return project_summary(project)


register(
    CommandSpec(
        name="project.list",
        help="列出所有项目（可按状态 / 名称筛选）",
        handler=_project_list,
        args=(
            ArgSpec(name="status", help="按状态筛选（如 进行中 / 已结账 / 编辑中）"),
            ArgSpec(name="name_contains", help="按名称包含子串筛选"),
        ),
        examples=("cpa project.list --json", "cpa project.list --status 进行中 --json"),
    )
)

register(
    CommandSpec(
        name="project.show",
        help="显示项目详情（默认含账单与工种明细）",
        handler=_project_show,
        args=(
            ArgSpec(name="uuid", help="项目 UUID", kind="positional"),
            ArgSpec(name="summary_only", help="仅输出摘要，不含账单明细", type="flag"),
        ),
        examples=(
            "cpa project.show <uuid> --json",
            "cpa project.show <uuid> --summary-only --json",
        ),
    )
)

register(
    CommandSpec(
        name="project.export",
        help="导出项目为 JSON 文件",
        handler=_project_export,
        read_only=False,
        args=(
            ArgSpec(name="uuid", help="项目 UUID", kind="positional"),
            ArgSpec(name="output", help="输出文件或目录路径", kind="positional"),
            ArgSpec(name="overwrite", help="允许覆盖已存在的目标文件", type="flag"),
        ),
        examples=("cpa project.export <uuid> ./out.json --json",),
    )
)

register(
    CommandSpec(
        name="project.import",
        help="从 JSON 文件导入项目",
        handler=_project_import,
        read_only=False,
        args=(ArgSpec(name="input", help="项目 JSON 文件路径", kind="positional"),),
        examples=("cpa project.import ./project.json --json",),
    )
)
