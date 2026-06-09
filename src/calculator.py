"""
公式解析与计算模块。

设计原则：区分三种公式形式
  1. 用户原始输入 (user_input)
     可包含全角/半角的 () [] {}, 也可以混用，支持 × ÷ 等中文运算符。
     可以有空格。只要求左右括号配对（不要求嵌套顺序）。
  2. 标准化公式 (canonical)
     程序内部使用。统一为半角小括号 ()，统一运算符为 + - * /，无空格。
     便于解析器处理。
  3. 标准化展示公式 (display)
     给用户看的。按中式数学习惯：3 层及以上最外层用大括号 {}、中括号 []
     包裹中间、最内层用小括号 ()；数字与运算符之间加空格；
     乘除显示为 × ÷。

主要 API:
  to_canonical(user_input, mapping)  -> 标准化公式
  evaluate_canonical(canonical)      -> 计算标准化公式
  evaluate(user_input, mapping)      -> 解析并计算用户输入
  to_display(canonical, extra_outer_layers=0) -> 转为展示形式
"""


class MathParseError(Exception):
    pass


_BRACKET_PAIR = {")": "(", "]": "[", "}": "{"}
_BRACKET_CLOSE = {"(": ")", "[": "]", "{": "}"}
_OPENERS = "([{"
_CLOSERS = ")]}"
_OPERATORS = "+-*/"


def to_canonical(user_input: str, mapping: dict | None = None) -> str:
    """
    用户输入 -> 标准化公式。
    - 应用字符映射（× -> *, 全角 -> 半角等）。
    - 去除空格。
    - 验证字符合法性。
    - 验证括号左右配对、类型匹配。
    - 所有 [] {} 统一转为 ()。
    - 验证语法合法性（可被解析器接受）。
    出错抛 MathParseError。
    """
    from .symbol_mapping import bracket_pair_maps, canonical_char_map
    char_map = canonical_char_map(mapping)
    open_to_close, close_to_open = bracket_pair_maps(mapping)

    if user_input is None:
        raise MathParseError("公式为空")

    stack = []
    cleaned = []
    for raw_ch in user_input:
        ch = char_map.get(raw_ch, raw_ch)
        if ch.isspace():
            continue
        if ch in _OPERATORS:
            cleaned.append(ch)
        elif ch.isdigit() or ch == ".":
            cleaned.append(ch)
        elif raw_ch in open_to_close:
            stack.append(raw_ch)
            cleaned.append("(")
        elif raw_ch in close_to_open:
            if not stack:
                raise MathParseError(f"多余的右括号: {raw_ch}")
            opener = stack.pop()
            if open_to_close[opener] != raw_ch:
                raise MathParseError(
                    f"括号不匹配: 左 {opener} 不能用右 {raw_ch} 闭合"
                )
            cleaned.append(")")
        else:
            raise MathParseError(f"非法字符: {ch!r}")

    if stack:
        unclosed = "".join(stack)
        raise MathParseError(f"未闭合的左括号: {unclosed}")

    canonical = "".join(cleaned)
    if not canonical:
        raise MathParseError("公式为空")

    _validate_canonical(canonical)
    return canonical


def _validate_canonical(canonical: str) -> None:
    """确保标准化公式可被解析（语法合法）。"""
    tokens = _tokenize(canonical)
    if not tokens:
        raise MathParseError("公式为空")
    _, pos = _parse_expr(tokens, 0)
    if pos != len(tokens):
        raise MathParseError(
            f"位置 {pos} 处出现意外标记: {tokens[pos]}"
        )


def _tokenize(canonical: str) -> list:
    """对标准化公式分词（只允许 0-9 . + - * / ( )）"""
    tokens = []
    i = 0
    n = len(canonical)
    while i < n:
        ch = canonical[i]
        if ch in "+-*/()":
            tokens.append(ch)
            i += 1
        elif ch.isdigit() or ch == ".":
            j = i
            while j < n and (canonical[j].isdigit() or canonical[j] == "."):
                j += 1
            num = canonical[i:j]
            if num.count(".") > 1:
                raise MathParseError(f"非法数字: {num}")
            if num == ".":
                raise MathParseError(f"非法数字: {num}")
            tokens.append(num)
            i = j
        else:
            raise MathParseError(f"非法字符: {ch!r}")
    return tokens


def _parse_factor(tokens: list, pos: int):
    if pos >= len(tokens):
        raise MathParseError("公式不完整")
    tok = tokens[pos]
    if tok == "(":
        val, pos = _parse_expr(tokens, pos + 1)
        if pos >= len(tokens) or tokens[pos] != ")":
            raise MathParseError("缺少右括号 )")
        return val, pos + 1
    if tok == "-":
        val, pos = _parse_factor(tokens, pos + 1)
        return -val, pos
    if tok == "+":
        return _parse_factor(tokens, pos + 1)
    try:
        return float(tok), pos + 1
    except ValueError:
        raise MathParseError(f"非法标记: {tok}")


def _parse_term(tokens: list, pos: int):
    val, pos = _parse_factor(tokens, pos)
    while pos < len(tokens) and tokens[pos] in "*/":
        op = tokens[pos]
        rhs, pos = _parse_factor(tokens, pos + 1)
        if op == "*":
            val *= rhs
        else:
            if rhs == 0:
                raise MathParseError("除以零")
            val /= rhs
    return val, pos


def _parse_expr(tokens: list, pos: int = 0):
    val, pos = _parse_term(tokens, pos)
    while pos < len(tokens) and tokens[pos] in "+-":
        op = tokens[pos]
        rhs, pos = _parse_term(tokens, pos + 1)
        if op == "+":
            val += rhs
        else:
            val -= rhs
    return val, pos


def evaluate_canonical(canonical: str) -> float:
    """计算标准化公式的数值。"""
    tokens = _tokenize(canonical)
    if not tokens:
        raise MathParseError("公式为空")
    val, pos = _parse_expr(tokens, 0)
    if pos != len(tokens):
        raise MathParseError(f"位置 {pos} 处意外标记: {tokens[pos]}")
    return val


def evaluate(user_input: str, mapping: dict | None = None) -> float:
    """用户输入 -> 计算结果。"""
    return evaluate_canonical(to_canonical(user_input, mapping))


def _max_depth(canonical: str) -> int:
    """计算标准化公式的最大括号嵌套深度。"""
    depth = 0
    cur = 0
    for ch in canonical:
        if ch == "(":
            cur += 1
            if cur > depth:
                depth = cur
        elif ch == ")":
            cur -= 1
    return depth


def _bracket_for_layer(layer_from_outer: int, total_depth: int) -> tuple:
    """
    根据中式数学习惯返回某一层应使用的括号 (open, close)。
    layer_from_outer: 1 = 最外层, total_depth = 最内层
    规则：
      - total_depth == 1: ()
      - total_depth == 2: 外 [], 内 ()
      - total_depth >= 3: 最内 (), 次内 [], 其余 {}
    """
    if total_depth <= 1:
        return ("(", ")")
    depth_from_inner = total_depth - layer_from_outer + 1
    if total_depth == 2:
        return ("(", ")") if depth_from_inner == 1 else ("[", "]")
    if depth_from_inner == 1:
        return ("(", ")")
    if depth_from_inner == 2:
        return ("[", "]")
    return ("{", "}")


def to_display(canonical: str, extra_outer_layers: int = 0) -> str:
    """
    标准化公式 -> 展示形式。
    - 按中式数学嵌套规则替换括号。
    - 数字与运算符之间加空格；乘除显示为 × ÷。
    - extra_outer_layers: 在最外层再加几层括号（用于乘以单价等场景）。
    """
    if not canonical:
        return ""

    inner_depth = _max_depth(canonical)
    total_depth = inner_depth + extra_outer_layers

    parts = []
    cur = 0
    for ch in canonical:
        if ch == "(":
            cur += 1
            layer = extra_outer_layers + cur
            o, _ = _bracket_for_layer(layer, total_depth)
            parts.append(o)
        elif ch == ")":
            layer = extra_outer_layers + cur
            _, c = _bracket_for_layer(layer, total_depth)
            parts.append(c)
            cur -= 1
        else:
            parts.append(ch)
    body = "".join(parts)

    for layer in range(extra_outer_layers, 0, -1):
        o, c = _bracket_for_layer(layer, total_depth)
        body = o + body + c

    return _add_spaces(body)


def _add_spaces(expr: str) -> str:
    """对带有 ()[]{} 和 + - * / 的表达式加空格、把 * / 显示成 × ÷。"""
    display_op = {"*": "×", "/": "÷", "+": "+", "-": "-"}
    tokens = []
    i = 0
    n = len(expr)
    while i < n:
        ch = expr[i]
        if ch in "+-*/" or ch in _OPENERS or ch in _CLOSERS:
            tokens.append(ch)
            i += 1
        elif ch.isdigit() or ch == ".":
            j = i
            while j < n and (expr[j].isdigit() or expr[j] == "."):
                j += 1
            tokens.append(expr[i:j])
            i = j
        else:
            i += 1

    out = []
    prev = None  # "num" | "open" | "close" | "op" | None
    for tok in tokens:
        if tok in _OPENERS:
            if prev in ("num", "close"):
                out.append(" ")
            out.append(tok)
            prev = "open"
        elif tok in _CLOSERS:
            out.append(tok)
            prev = "close"
        elif tok in "+-*/":
            is_unary = tok in "+-" and (prev is None or prev == "op" or prev == "open")
            if is_unary:
                out.append(display_op[tok])
            else:
                out.append(" ")
                out.append(display_op[tok])
                out.append(" ")
            prev = "op"
        else:
            out.append(tok)
            prev = "num"
    return "".join(out)


def normalize_expression(expr: str, mapping: dict | None = None) -> str:
    """向后兼容：返回标准化公式。出错时返回原字符串。"""
    try:
        return to_canonical(expr, mapping)
    except MathParseError:
        return expr


def evaluate_with_mapping(expr: str, mapping: dict | None = None) -> float:
    """向后兼容：用户输入 -> 计算结果。"""
    return evaluate(expr, mapping)
