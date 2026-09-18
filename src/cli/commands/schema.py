"""`schema` 命令：输出机器可读的说明书。

这是"让其他程序方便调用"的核心：调用方先读 schema 发现能力与参数，
不必依赖人工维护的文档。schema 由 registry 遍历生成，不会与实现漂移。
"""
from __future__ import annotations

import argparse

from ..registry import CommandSpec, build_schema, register


def _schema(args: argparse.Namespace) -> dict:
    return build_schema()


register(
    CommandSpec(
        name="schema",
        help="输出机器可读的能力清单（命令、参数、响应契约）",
        handler=_schema,
        read_only=True,
        examples=("cpa schema --json",),
    )
)
