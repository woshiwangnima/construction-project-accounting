import json
import os

from .logger import logger
from .utils import atomic_write_json
from .versioning import APP_VERSION, CURRENT_SCHEMA_VERSION
from .symbol_mapping import DEFAULT_SYMBOL_MAPPING

CONFIG_DIR = os.environ.get("CPA_CONFIG_DIR", os.path.join(os.path.dirname(os.path.dirname(__file__)), "config"))

_DEFAULT_CONFIGS = {
    "app_config.json": {
        "app_version": APP_VERSION,
        "schema_version": CURRENT_SCHEMA_VERSION,
        "button_font_size": 16,
        "symbol_mapping": DEFAULT_SYMBOL_MAPPING,
        "window_sizes": {
            "settings": [900, 700],
            "rollback": [1200, 650],
            "new_project": [640, 420],
        },
        "export_defaults": {
            "price_list_settings": {
                "visible": True,
                "show_no_unit_items": False,
                "show_empty_categories": False,
                "align_columns": True,
                "name_width": 12,
                "price_width": 10,
            },
            "text_colors": {
                "normal": "#000000",
                "muted": "#888888",
                "formula": "#2b6cb0",
                "amount": "#c0392b",
            },
            "export_bg_color": "#ffffff",
            "export_strip_category": True,
            "export_show_project_date": False,
            "export_show_record_time": False,
            "export_show_export_time": False,
            "export_append_note_to_item_title": True,
        },
        "voice": {
            "enabled": True,
            "volume": 80,
            "tts_rate": 150,
            "preview_text": "砌墙，公式，12.5 乘以 3 加 8 除以 2 减去括号 1.5 加 0.5 括号，等于 41.5",
        },
        "backup_count": 10,
        "default_bill_column_widths": {
            "#": 0.0526315789,
            "工作内容": 0.1394736842,
            "公式": 0.1263157895,
            "单价": 0.1263157895,
            "金额": 0.1263157895,
            "备注": 0.1684210526,
            "日期": 0.1263157895,
            "操作": 0.0842105263,
        },
        # 工作类型表的默认列宽（被「工作类型」界面读取，与项目文件 worker_column_widths 互不冲突）
        "default_worker_column_widths": {
            "名称": 0.3571428571,    # 5/14
            "单价": 0.2142857143,    # 3/14
            "单位": 0.2142857143,
            "计费类型": 0.2142857143,
            "操作": 0.12,
        },
        # 列表中单条数据选中后的高亮底色。
        # 覆盖范围：账单管理（BillListView）+ 工作类型（worker Treeview）。
        # 选 "#90cdf4" 是 Tailwind blue-300，明显但 #1a202c 黑字仍清晰可读。
        "selection_highlight_color": "#90cdf4",
        "bill_reviewed_row_color": "#e6fffa",
        "rollback_column_widths": {
            "序号": 0.07,
            "上次修改时间": 0.17,
            "项目状态": 0.10,
            "有效性": 0.13,
            "工作数量情况": 0.35,
            "账单数": 0.18,
        },
        "default_categories": [],
        # 默认工作项目列表。新格式使用 category_id 关联 default_categories。
        # 仍兼容旧格式 category 字符串。
        "default_trade_items": [],
        "release_notes": [
            {
                "version": APP_VERSION,
                "date": "2026-06-08",
                "notes": ["新增统一符号映射设置", "新增关于页面", "优化列宽与拖拽体验"],
            }
        ],
    },
    "user_config.json": {
        "app_version": APP_VERSION,
        "schema_version": CURRENT_SCHEMA_VERSION,
        "window_sizes": {},
    },
}


def _safe_path(filename: str) -> str:
    if os.sep in filename or "/" in filename or ".." in filename:
        raise ValueError(f"Invalid config filename: {filename}")
    return os.path.join(CONFIG_DIR, filename)


def load_json(filename: str) -> dict:
    path = _safe_path(filename)
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        logger.warning("Config file not found: %s, using defaults", filename)
        return _DEFAULT_CONFIGS.get(filename, {})
    except json.JSONDecodeError as e:
        logger.error("Invalid JSON in %s: %s", filename, e)
        return _DEFAULT_CONFIGS.get(filename, {})
    except OSError as e:
        logger.error("Failed to read config %s: %s", filename, e)
        return _DEFAULT_CONFIGS.get(filename, {})


def load_app():
    return load_json("app_config.json")


def load_user():
    return load_json("user_config.json")


def save_user(data: dict):
    path = _safe_path("user_config.json")
    atomic_write_json(path, data)


def save_app(data: dict):
    path = _safe_path("app_config.json")
    atomic_write_json(path, data)
