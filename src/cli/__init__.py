"""命令行接口（不依赖 Qt / 不启动 GUI）。

约束（由 tests/test_cli_no_qt.py 守住）：
本包内任何模块都不得 import PySide6 / qfluentwidgets / qtawesome，
也不得 import src.gui.**。这样 CLI 才能在无显示器环境、CI、以及被
其他程序当作子进程调用时正常工作。
"""

from __future__ import annotations

from . import commands  # noqa: F401  触发命令注册
from .registry import all_commands, build_parser, build_schema

__all__ = ["all_commands", "build_parser", "build_schema", "main"]


def main(argv: list[str] | None = None, prog: str = "cpa") -> int:
    """CLI 入口。返回退出码（不调用 sys.exit，方便测试）。"""
    import sys

    from .output import emit_json, ok_payload, run_command
    from .registry import get_command

    parser = build_parser(prog)
    args = parser.parse_args(argv)

    if not getattr(args, "command", None):
        parser.print_help()
        return 2

    spec = get_command(args.command)
    if spec is None:  # pragma: no cover - argparse 已保证命令存在
        parser.error(f"未知命令: {args.command}")
        return 2

    # 顶层 --json 与子命令 --json 都接受（子命令用 SUPPRESS 默认值，
    # 因此这里取到的 True 一定来自用户显式传入）
    as_json = bool(getattr(args, "json", False))

    if args.command == "schema":
        payload = build_schema(prog)
        if as_json:
            emit_json(ok_payload(payload), sys.stdout)
        else:
            emit_json(payload, sys.stdout)
        return 0

    return run_command(spec.handler, args, as_json)


if __name__ == "__main__":  # pragma: no cover
    import sys

    sys.exit(main())
