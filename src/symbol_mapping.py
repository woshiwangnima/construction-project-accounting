from __future__ import annotations


DEFAULT_SYMBOL_MAPPING = {
    "operators": {
        "+": {"label": "加", "aliases": ["＋"], "voice_key": "+"},
        "-": {"label": "减", "aliases": ["－"], "voice_key": "-"},
        "*": {"label": "乘", "aliases": ["×", "X", "x", "·"], "voice_key": "×"},
        "/": {"label": "除", "aliases": ["÷", "／"], "voice_key": "÷"},
    },
    "bracket_pairs": [
        {"left": "(", "right": ")", "left_label": "左括号", "right_label": "右括号", "voice_left_key": "(", "voice_right_key": ")"},
        {"left": "[", "right": "]", "left_label": "左中括号", "right_label": "右中括号", "voice_left_key": "(", "voice_right_key": ")"},
        {"left": "{", "right": "}", "left_label": "左大括号", "right_label": "右大括号", "voice_left_key": "(", "voice_right_key": ")"},
        {"left": "（", "right": "）", "left_label": "左括号", "right_label": "右括号", "voice_left_key": "(", "voice_right_key": ")"},
        {"left": "【", "right": "】", "left_label": "左中括号", "right_label": "右中括号", "voice_left_key": "(", "voice_right_key": ")"},
        {"left": "｛", "right": "｝", "left_label": "左大括号", "right_label": "右大括号", "voice_left_key": "(", "voice_right_key": ")"},
    ],
}


def _single_char(value: str, label: str) -> str:
    value = str(value or "")
    if len(value) != 1:
        raise ValueError(f"{label} 必须是单字符")
    return value


def normalize_symbol_mapping(mapping: dict | None) -> dict:
    src = mapping or DEFAULT_SYMBOL_MAPPING
    operators = src.get("operators", {}) or {}
    result_ops = {}
    for canonical in ("+", "-", "*", "/"):
        raw = operators.get(canonical, {}) or {}
        aliases = []
        seen = {canonical}
        for alias in raw.get("aliases", []) or []:
            ch = _single_char(alias, f"{canonical} alias")
            if ch not in seen:
                aliases.append(ch)
                seen.add(ch)
        result_ops[canonical] = {
            "label": str(raw.get("label") or {"+": "加", "-": "减", "*": "乘", "/": "除"}[canonical]),
            "aliases": aliases,
            "voice_key": str(raw.get("voice_key") or ({"*": "×", "/": "÷"}.get(canonical, canonical))),
        }
    pairs = []
    for pair in src.get("bracket_pairs", []) or []:
        left = _single_char(pair.get("left"), "左括号")
        right = _single_char(pair.get("right"), "右括号")
        pairs.append({
            "left": left,
            "right": right,
            "left_label": str(pair.get("left_label") or "左括号"),
            "right_label": str(pair.get("right_label") or "右括号"),
            "voice_left_key": str(pair.get("voice_left_key") or "("),
            "voice_right_key": str(pair.get("voice_right_key") or ")"),
        })
    return {"operators": result_ops, "bracket_pairs": pairs}


def canonical_char_map(mapping: dict | None) -> dict[str, str]:
    normalized = normalize_symbol_mapping(mapping)
    result = {}
    for canonical, info in normalized["operators"].items():
        result[canonical] = canonical
        for alias in info.get("aliases", []):
            result[alias] = canonical
    for pair in normalized["bracket_pairs"]:
        result[pair["left"]] = "("
        result[pair["right"]] = ")"
    return result


def bracket_pair_maps(mapping: dict | None) -> tuple[dict[str, str], dict[str, str]]:
    normalized = normalize_symbol_mapping(mapping)
    open_to_close = {}
    close_to_open = {}
    for pair in normalized["bracket_pairs"]:
        open_to_close[pair["left"]] = pair["right"]
        close_to_open[pair["right"]] = pair["left"]
    return open_to_close, close_to_open


def voice_speakable_map(mapping: dict | None) -> dict[str, str]:
    normalized = normalize_symbol_mapping(mapping)
    result = {}
    for canonical, info in normalized["operators"].items():
        label = info.get("label", canonical)
        result[canonical] = label
        result[info.get("voice_key", canonical)] = label
        for alias in info.get("aliases", []):
            result[alias] = label
    for pair in normalized["bracket_pairs"]:
        result[pair["left"]] = pair["left_label"]
        result[pair["right"]] = pair["right_label"]
    return result


def voice_key_for_char(ch: str, mapping: dict | None) -> str | None:
    normalized = normalize_symbol_mapping(mapping)
    for canonical, info in normalized["operators"].items():
        if ch == canonical or ch in info.get("aliases", []) or ch == info.get("voice_key"):
            return info.get("voice_key", canonical)
    for pair in normalized["bracket_pairs"]:
        if ch == pair["left"]:
            return pair.get("voice_left_key", "(")
        if ch == pair["right"]:
            return pair.get("voice_right_key", ")")
    return ch if ch.isdigit() or ch in {".", "清空", "删除"} else None
