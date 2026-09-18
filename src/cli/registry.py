"""命令注册表：命令定义的唯一来源。

设计目的
--------
`cpa schema`（机器可读说明书）与 argparse 子命令都由这里遍历生成，
不允许手写第二份命令清单——手写文档会随代码腐烂，且没有任何测试
能发现文档与实现不一致（参见 AGENTS.md 里字号表两次各写一份的教训）。
"""
from __future__ import annotations

import argparse
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class ArgSpec:
    """一个位置参数或选项的参数说明。"""

    name: str
    help: str
    kind: str = "option"  # "option" | "positional"
    type: str = "str"  # "str" | "int" | "flag"
    required: bool = False
    default: Any = None
    choices: tuple[str, ...] | None = None

    def add_to(self, parser: argparse.ArgumentParser) -> None:
        kwargs: dict[str, Any] = {"help": self.help}
        if self.default is not None:
            kwargs["default"] = self.default
        if self.choices:
            kwargs["choices"] = list(self.choices)

        if self.kind == "positional":
            parser.add_argument(self.name, **kwargs)
            return

        flag = "--" + self.name.replace("_", "-")
        if self.type == "flag":
            kwargs["action"] = "store_true"
            if self.default is None:
                kwargs["default"] = False
        elif self.type == "int":
            kwargs["type"] = int
        parser.add_argument(flag, **kwargs)

    def to_schema(self) -> dict:
        schema: dict[str, Any] = {
            "name": self.name,
            "kind": self.kind,
            "type": self.type,
            "help": self.help,
        }
        if self.required:
            schema["required"] = True
        if self.choices:
            schema["choices"] = list(self.choices)
        return schema


@dataclass(frozen=True)
class CommandSpec:
    """一个命令的完整定义。"""

    name: str
    help: str
    handler: Callable[[argparse.Namespace], Any]
    args: tuple[ArgSpec, ...] = field(default_factory=tuple)
    read_only: bool = True
    examples: tuple[str, ...] = field(default_factory=tuple)

    def to_schema(self) -> dict:
        return {
            "name": self.name,
            "help": self.help,
            "readOnly": self.read_only,
            "args": [arg.to_schema() for arg in self.args],
            "examples": list(self.examples),
        }


_REGISTRY: dict[str, CommandSpec] = {}


def register(spec: CommandSpec) -> CommandSpec:
    if spec.name in _REGISTRY:
        raise ValueError(f"重复注册命令: {spec.name}")
    _REGISTRY[spec.name] = spec
    return spec


def all_commands() -> list[CommandSpec]:
    return sorted(_REGISTRY.values(), key=lambda spec: spec.name)


def get_command(name: str) -> CommandSpec | None:
    return _REGISTRY.get(name)


def build_parser(prog: str = "cpa") -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog=prog,
        description="施工项目记账程序 命令行接口（不启动 GUI）",
    )
    parser.add_argument("--json", action="store_true", help="以 JSON 输出（程序调用请始终使用）")
    subparsers = parser.add_subparsers(dest="command", metavar="<command>")

    for spec in all_commands():
        sub = subparsers.add_parser(spec.name, help=spec.help)
        sub.add_argument(
            "--json",
            action="store_true",
            default=argparse.SUPPRESS,
            help=argparse.SUPPRESS,
        )
        for arg in spec.args:
            arg.add_to(sub)

    return parser


def build_schema(prog: str = "cpa") -> dict:
    """生成机器可读说明书（供其他程序 / AI 自动发现能力）。"""
    return {
        "program": prog,
        "responseContract": {
            "success": {"ok": True, "data": "<any>"},
            "failure": {"ok": False, "error": {"code": "<string>", "message": "<string>"}},
            "exitCodes": {"0": "成功", "1": "业务错误（响应体仍是 JSON）", "2": "参数错误"},
        },
        "commands": [spec.to_schema() for spec in all_commands()],
    }
