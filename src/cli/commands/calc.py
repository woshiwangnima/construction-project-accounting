"""`calc` 命令：算式求值，不读写任何项目文件。"""
from __future__ import annotations

import argparse

from ...calculator import evaluate_decimal, to_canonical
from ..common import op_map
from ..errors import FormulaError
from ..registry import ArgSpec, CommandSpec, register


def _calc(args: argparse.Namespace) -> dict:
    expression = args.expression
    mapping = op_map()
    try:
        canonical = to_canonical(expression, mapping)
        value = evaluate_decimal(canonical)
        result = float(value)
    except Exception as exc:
        raise FormulaError(f"算式无法求值: {expression}", details={"reason": str(exc)}) from exc

    return {
        "input": expression,
        "canonical": canonical,
        "result": result,
        # 金额口径与账单一致：保留两位、四舍五入
        "amount": round(result, 2),
    }


register(
    CommandSpec(
        name="calc",
        help="计算算式（支持 × ÷ 全角符号与括号）",
        handler=_calc,
        read_only=True,
        args=(
            ArgSpec(
                name="expression",
                help="算式，例如 3*4+5 或 （2+3）×4",
                kind="positional",
            ),
        ),
        examples=("cpa calc 3*4+5 --json", "cpa calc '（2+3）×4' --json"),
    )
)
