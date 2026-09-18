"""分类 / 列宽解析的纯函数（自 content.py 抽出，不依赖 Qt）。"""
from ...config_loader import load_app


def _category_name(category) -> str:
    if hasattr(category, "name"):
        return category.name
    if isinstance(category, dict):
        return category.get("name", "")
    return str(category)
def _category_id(category) -> str:
    if hasattr(category, "id"):
        return category.id
    if isinstance(category, dict):
        return category.get("id", "")
    return ""
def _category_maps(project) -> tuple[dict[str, str], dict[str, str]]:
    id_to_name = {}
    name_to_id = {}
    for category in (project or {}).get("category_order", []) or []:
        cid = _category_id(category)
        name = _category_name(category)
        if cid:
            id_to_name[cid] = name
        if name:
            name_to_id[name] = cid
    return id_to_name, name_to_id
def _trade_item_category_name(item, project, category_maps=None) -> str:
    if item.get("category"):
        return item.get("category", "")
    id_to_name, _ = category_maps or _category_maps(project)
    return id_to_name.get(item.get("category_id", ""), item.get("category_id", ""))
def _project_category_names(project) -> list[str]:
    category_maps = _category_maps(project)
    names = [_category_name(c) for c in (project or {}).get("category_order", []) or []]
    for item in (project or {}).get("trade_items", []) or []:
        name = _trade_item_category_name(item, project, category_maps)
        if name and name not in names:
            names.append(name)
    return names
def _safe_positive_float(v) -> float | None:
    try:
        x = float(v)
        if x > 0:
            return x
    except (TypeError, ValueError):
        pass
    return None
def resolve_bill_columns(
    project_data: dict,
    app_config: dict | None = None,
) -> tuple[list[str], dict[str, float], list[str]]:
    """返回 (列顺序, 当前模式权重[全部11列], 隐藏列列表)。与 Tk 版一致。"""
    app_config = app_config if app_config is not None else load_app()
    defaults = app_config.get("default_bill_column_widths_data", [])
    columns = [d["name"] for d in defaults]

    saved = (project_data or {}).get("bill_column_widths", []) or []
    saved_map = {}
    for item in saved:
        if isinstance(item, dict) and "name" in item:
            w = _safe_positive_float(item.get("weight"))
            if w is not None:
                saved_map[item["name"]] = w

    base = {}
    for d in defaults:
        base[d["name"]] = saved_map.get(d["name"], d["weight"])

    mode = (project_data or {}).get("bill_display_mode", "simple")
    visible = (project_data or {}).get("bill_visible_columns") or []
    if visible:
        visible_set = set(visible)
        hidden = [c for c in columns if c not in visible_set]
        hidden = [c for c in hidden if c != BILL_ACTION_COL]
    elif mode == "simple":
        hidden = [d["name"] for d in defaults if not d.get("show_in_simple", True)]
    elif mode == "audit":
        hidden = [d["name"] for d in defaults if not d.get("show_in_audit", True)]
    else:
        hidden = []
    if not hidden:
        return columns, base, []

    visible = [c for c in columns if c not in hidden]
    total_hidden = sum(base[c] for c in hidden)
    total_visible = sum(base[c] for c in visible)

    if total_visible <= 0:
        return columns, base, hidden

    ratio = 1 + total_hidden / total_visible
    weights = {}
    for col in columns:
        weights[col] = base.get(col, 0) * ratio if col in visible else base.get(col, 0)

    return columns, weights, hidden
def resolve_worker_column_weights(project_data: dict, app_config: dict | None = None) -> dict:
    """解析 worker 表格列权重：项目保存值 → app_config 默认 → 硬编码。"""
    saved = (project_data or {}).get("worker_column_widths", {}) or {}
    try:
        app_config = app_config if app_config is not None else load_app()
        app_defaults = app_config.get("default_worker_column_widths", {}) or {}
    except Exception:
        app_defaults = {}

    result: dict[str, float] = {}
    for col in WORKER_COLUMNS:
        w = _safe_positive_float(saved.get(col))
        if w is not None:
            result[col] = w
            continue
        w = _safe_positive_float(app_defaults.get(col))
        if w is not None:
            result[col] = w
            continue
        result[col] = WORKER_DEFAULT_WEIGHTS[col]
    return result


# ── 工种列定义（自 content.py 移入）─────────────────────────────────────────

WORKER_COLUMNS = ("名称", "单价", "单位", "计费类型", "操作")

WORKER_DEFAULT_WEIGHTS = {
    "名称": 0.3571428571,    # 5/14
    "单价": 0.2142857143,    # 3/14
    "单位": 0.2142857143,
    "计费类型": 0.2142857143,
    "操作": 0.06,
}

BILL_ACTION_COL = "操作"
