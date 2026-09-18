"""统一输出契约。

规则（调用方依赖，改动需同步 tests/test_cli_contract.py）：

- 成功：{"ok": true,  "data": ...}     退出码 0
- 失败：{"ok": false, "error": {"code": ..., "message": ...}}  退出码 1

`--json` 决定的是渲染方式，不是数据结构：两种模式共用同一个 dict，
避免"人看的"和"程序看的"两套逻辑漂移。错误同样走 JSON（而不是只写
stderr 的纯文本），否则调用方必须解析两种格式。
"""

from __future__ import annotations

import json
import sys
from typing import Any

from .errors import EXIT_ERROR, EXIT_OK, CliError


def ok_payload(data: Any) -> dict:
    return {"ok": True, "data": data}


def error_payload(error: CliError) -> dict:
    return {"ok": False, "error": error.to_payload()}


def emit_json(payload: dict, stream=None) -> None:
    stream = stream or sys.stdout
    json.dump(payload, stream, ensure_ascii=False, indent=2, allow_nan=False)
    stream.write("\n")


def emit_text(data: Any, stream=None) -> None:
    """人类可读渲染。只做展示，不参与程序间契约。"""
    stream = stream or sys.stdout
    stream.write(_render(data))
    if not _render(data).endswith("\n"):
        stream.write("\n")


def _render(data: Any) -> str:
    if data is None:
        return "(无数据)"
    if isinstance(data, str):
        return data
    if isinstance(data, dict):
        lines = []
        for key, value in data.items():
            if isinstance(value, (dict, list)):
                nested = _render(value)
                lines.append(f"{key}:")
                lines.extend("  " + line for line in nested.splitlines())
            else:
                lines.append(f"{key}: {value}")
        return "\n".join(lines) if lines else "(空)"
    if isinstance(data, list):
        if not data:
            return "(空列表)"
        blocks = []
        for index, item in enumerate(data, 1):
            blocks.append(f"[{index}]")
            blocks.extend("  " + line for line in _render(item).splitlines())
        return "\n".join(blocks)
    return str(data)


def run_command(func, args, as_json: bool) -> int:
    """执行命令并统一落地输出与退出码。命令函数返回可序列化数据。"""
    try:
        data = func(args)
    except CliError as exc:
        if as_json:
            emit_json(error_payload(exc), sys.stdout)
        else:
            sys.stderr.write(f"错误 [{exc.code}]: {exc.message}\n")
        return EXIT_ERROR
    except Exception as exc:  # noqa: BLE001
        # 兜底：这里是进程与调用方的边界，任何意外异常都必须转成契约内的
        # JSON 错误，绝不让调用方拿到半截 JSON 或裸 traceback。
        wrapped = CliError(f"{type(exc).__name__}: {exc}")
        if as_json:
            emit_json(error_payload(wrapped), sys.stdout)
        else:
            sys.stderr.write(f"错误 [{wrapped.code}]: {wrapped.message}\n")
        return EXIT_ERROR

    if as_json:
        emit_json(ok_payload(data), sys.stdout)
    else:
        emit_text(data, sys.stdout)
        sys.stdout.write("\n")
    return EXIT_OK
