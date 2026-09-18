"""CLI 错误类型与错误码。

错误码是给调用方（脚本 / 其他程序 / AI）用的稳定契约，不要随意改动字符串值；
新增错误时只追加，不复用已有码。
"""
from __future__ import annotations

# 退出码约定（与 argparse 保持一致：2 保留给参数错误）
EXIT_OK = 0
EXIT_ERROR = 1
EXIT_USAGE = 2


class CliError(Exception):
    """业务错误：会被 output.py 序列化成 {"ok": false, "error": {...}}。"""

    code = "ERROR"

    def __init__(self, message: str, code: str | None = None, details: dict | None = None):
        super().__init__(message)
        self.message = message
        if code:
            self.code = code
        self.details = details or {}

    def to_payload(self) -> dict:
        payload: dict[str, object] = {"code": self.code, "message": self.message}
        if self.details:
            payload["details"] = self.details
        return payload


class ProjectNotFound(CliError):
    code = "PROJECT_NOT_FOUND"


class InvalidArgument(CliError):
    code = "INVALID_ARGUMENT"


class FormulaError(CliError):
    code = "FORMULA_ERROR"


class ExportFailed(CliError):
    code = "EXPORT_FAILED"
