"""FontManager: dynamic font resolution with live-update support (Qt).

Usage:
    from .font_manager import font_manager

    # Qt 应用（src.gui.qt）：
    font_manager.init_qt(on_refresh=cb)

    # In widgets:
    font=font_manager.get("body")          # → QFont
    fg=font_manager.get_color("body")      # → theme.TEXT_PRIMARY

    # Settings panel triggers refresh after save:
    font_manager.refresh()
"""

from __future__ import annotations

from ..logger import logger
from .theme import TEXT_PRIMARY, TEXT_SECONDARY

# ── 角色定义 ──────────────────────────────────────────────────────────────────
# 每个角色对应一组 theme.py 常量，可独立配置字体族/字号/加粗/斜体/下划线/删除线/颜色。

ROLE_KEYS = ("icon_btn", "dialog_btn", "entry_item", "button", "calc_btn",
             "title", "heading", "subheading",
             "body", "body_bold",
             "tree", "tree_header", "small", "amount")

ROLE_DISPLAY_NAMES = {
    "icon_btn": "图标按钮",
    "dialog_btn": "对话框按钮",
    "entry_item": "状态条目",
    "button": "通用按钮",
    "calc_btn": "计算器按键",
    "title": "一级标题",
    "heading": "二级标题",
    "subheading": "三级标题",
    "body": "正文",
    "body_bold": "正文加粗",
    "tree": "表格行",
    "tree_header": "表格表头",
    "small": "辅助文字",
    "amount": "大数字(总金额)",
}

# 5 个分组（用于设置面板 UI 分区）
ROLE_GROUPS = [
    ("按钮类", ("icon_btn", "dialog_btn", "entry_item", "button", "calc_btn")),
    ("标题类", ("title", "heading", "subheading", "amount")),
    ("正文类", ("body", "body_bold")),
    ("表格类", ("tree", "tree_header")),
    ("辅助", ("small",)),
]

# 字号乘数：effective_size = round(default_font_size * multiplier)
_ROLE_SIZE_MULTIPLIERS = {
    "icon_btn":    1.0,
    "dialog_btn":  1.0,
    "entry_item":  1.0,
    "button":      1.0,
    "calc_btn":    1.29,
    "title":       1.57,
    "heading":     1.2,
    "subheading":  1.07,
    "body":        1.0,
    "body_bold":   1.0,
    "tree":        1.0,
    "tree_header": 1.0,
    "small":       0.86,
    "amount":      2.0,
}

_DEFAULT_FONT_SIZE = 14

_ROLE_DEFAULTS = {
    "icon_btn":    {"family": "Microsoft YaHei UI", "size": 14, "bold": True,  "italic": False, "underline": False, "overstrike": False, "color": TEXT_PRIMARY},
    "dialog_btn":  {"family": "Microsoft YaHei UI", "size": 14, "bold": True,  "italic": False, "underline": False, "overstrike": False, "color": TEXT_PRIMARY},
    "entry_item":  {"family": "Microsoft YaHei UI", "size": 14, "bold": True,  "italic": False, "underline": False, "overstrike": False, "color": TEXT_PRIMARY},
    "title":       {"family": "Microsoft YaHei UI", "size": 22, "bold": True,  "italic": False, "underline": False, "overstrike": False, "color": TEXT_PRIMARY},
    "heading":     {"family": "Microsoft YaHei UI", "size": 17, "bold": True,  "italic": False, "underline": False, "overstrike": False, "color": TEXT_PRIMARY},
    "subheading":  {"family": "Microsoft YaHei UI", "size": 15, "bold": True,  "italic": False, "underline": False, "overstrike": False, "color": TEXT_PRIMARY},
    "body":        {"family": "Microsoft YaHei UI", "size": 14, "bold": False, "italic": False, "underline": False, "overstrike": False, "color": TEXT_PRIMARY},
    "body_bold":   {"family": "Microsoft YaHei UI", "size": 14, "bold": True,  "italic": False, "underline": False, "overstrike": False, "color": TEXT_PRIMARY},
    "button":      {"family": "Microsoft YaHei UI", "size": 14, "bold": True,  "italic": False, "underline": False, "overstrike": False, "color": "#ffffff"},
    "calc_btn":    {"family": "Microsoft YaHei UI", "size": 18, "bold": True,  "italic": False, "underline": False, "overstrike": False, "color": TEXT_PRIMARY},
    "tree":        {"family": "Microsoft YaHei UI", "size": 14, "bold": False, "italic": False, "underline": False, "overstrike": False, "color": TEXT_PRIMARY},
    "tree_header": {"family": "Microsoft YaHei UI", "size": 14, "bold": True,  "italic": False, "underline": False, "overstrike": False, "color": TEXT_PRIMARY},
    "small":       {"family": "Microsoft YaHei UI", "size": 12, "bold": False, "italic": False, "underline": False, "overstrike": False, "color": TEXT_SECONDARY},
    "amount":      {"family": "Microsoft YaHei UI", "size": 28, "bold": True,  "italic": False, "underline": False, "overstrike": False, "color": TEXT_PRIMARY},
}


def _build_qfont(cfg: dict):
    """Convert a merged font config dict to a QFont.

    字号统一按**像素**处理：角色 size 由 base_size(default_font_size, 单位 px)
    乘以角色倍率算出，而 QSS 侧用的也是 ``font-size: Npx``。若这里用
    ``setPointSize``，表格单元格（走 model 的 FontRole）会比界面其它文字
    大约三分之一，造成同一屏内字号不一致、列宽被撑爆。
    """
    from PySide6.QtGui import QFont
    font = QFont()
    font.setFamily(cfg.get("family", "Microsoft YaHei UI"))
    font.setPixelSize(max(1, int(cfg.get("size", 14))))
    font.setWeight(QFont.Weight.Bold if cfg.get("bold") else QFont.Weight.Normal)
    font.setItalic(bool(cfg.get("italic")))
    font.setUnderline(bool(cfg.get("underline")))
    font.setStrikeOut(bool(cfg.get("overstrike")))
    return font


class FontManager:
    """Singleton font manager — creates and manages QFont objects."""

    def __init__(self):
        self._fonts: dict[str, object] = {}
        self._colors: dict[str, str] = {}
        self._initialized = False
        self._qt_refresh_callback = None

    def init_qt(self, on_refresh=None) -> None:
        """Qt 模式初始化：on_refresh 为 refresh() 时的回调（重放字体/QSS）。

        重复调用是安全的：回调始终会被更新，但字体只构建一次。
        """
        if on_refresh is not None:
            self._qt_refresh_callback = on_refresh
        if self._initialized:
            return
        self._build_fonts()
        self._initialized = True
        logger.debug("[font_manager] initialized %d roles", len(self._fonts))

    def _build_fonts(self) -> None:
        """Build (or rebuild) font objects from config + defaults.

        Effective size = round(default_font_size * multiplier) for each role.
        Size is always computed from the global multiplier — user overrides
        apply to family, bold, italic, underline, overstrike, color, but NOT size.
        """
        dfs = self._load_default_font_size()
        user_fonts = self._load_user_fonts()
        for role in ROLE_KEYS:
            mult = _ROLE_SIZE_MULTIPLIERS.get(role, 1.0)
            base_size = max(8, round(dfs * mult))
            defaults = {**_ROLE_DEFAULTS[role], "size": base_size}
            user = user_fonts.get(role, {})
            # Merge user overrides but ALWAYS use multiplier-computed size
            user_no_size = {k: v for k, v in user.items() if k != "size"}
            merged = {**defaults, **user_no_size}
            color = merged.get("color", defaults["color"])
            self._fonts[role] = _build_qfont(merged)
            self._colors[role] = color

    def _load_user_fonts(self) -> dict:
        """Load font_settings from user_config.json."""
        try:
            from ..config_loader import load_user
            return load_user().get("font_settings", {})
        except Exception:
            return {}

    def _load_default_font_size(self) -> int:
        """Read default_font_size from app_config."""
        try:
            from ..config_loader import load_app
            return int(load_app().get("default_font_size", _DEFAULT_FONT_SIZE))
        except Exception:
            return _DEFAULT_FONT_SIZE

    # ── Public API ────────────────────────────────────────────────────────────

    def get_default_font_size(self) -> int:
        """Return the current default_font_size from app_config."""
        return self._load_default_font_size()

    def save_default_font_size(self, size: int) -> None:
        """Write default_font_size to app_config and refresh all fonts."""
        try:
            from ..config_loader import load_app, save_app
            cfg = load_app()
            cfg["default_font_size"] = max(10, min(30, int(size)))
            save_app(cfg)
        except Exception as e:
            logger.warning("[font_manager] save default_font_size failed: %s", e)
        self.refresh()

    def get(self, role: str) -> object:
        """Return the QFont for a role. Falls back to 'body'."""
        if not self._initialized:
            return _build_qfont(_ROLE_DEFAULTS.get(role, _ROLE_DEFAULTS["body"]))
        return self._fonts.get(role, self._fonts.get("body"))

    def get_color(self, role: str) -> str:
        """Return the configured color for a role."""
        if not self._initialized:
            return _ROLE_DEFAULTS.get(role, _ROLE_DEFAULTS["body"])["color"]
        return self._colors.get(role, _ROLE_DEFAULTS.get(role, _ROLE_DEFAULTS["body"])["color"])

    def refresh(self) -> None:
        """Re-read user_config and rebuild all QFont objects.

        QFont 是值对象，无法原地更新，因此通过 on_refresh 回调让应用重新应用字体/QSS。
        """
        if not self._initialized:
            return
        self._build_fonts()
        if callable(self._qt_refresh_callback):
            try:
                self._qt_refresh_callback()
            except Exception as e:
                logger.warning("[font_manager] qt refresh callback failed: %s", e)
        logger.debug("[font_manager] refreshed %d roles", len(self._fonts))

    def reset_all(self) -> None:
        """Remove font_settings from user_config and restore all defaults."""
        try:
            from ..config_loader import load_user, save_user
            cfg = load_user()
            cfg.pop("font_settings", None)
            save_user(cfg)
        except Exception as e:
            logger.warning("[font_manager] reset failed: %s", e)
        self.refresh()

    def get_all_settings(self) -> dict:
        """Return the effective font settings for all roles.

        Size is always computed from default_font_size * multiplier.
        User overrides apply to non-size properties only.
        """
        dfs = self._load_default_font_size()
        user = self._load_user_fonts()
        result = {}
        for role in ROLE_KEYS:
            mult = _ROLE_SIZE_MULTIPLIERS.get(role, 1.0)
            base_size = max(8, round(dfs * mult))
            defaults = {**_ROLE_DEFAULTS[role], "size": base_size}
            user_role = user.get(role, {})
            user_no_size = {k: v for k, v in user_role.items() if k != "size"}
            merged = {**defaults, **user_no_size}
            result[role] = {
                "family": merged.get("family", defaults["family"]),
                "size": int(merged.get("size", defaults["size"])),
                "bold": bool(merged.get("bold", defaults["bold"])),
                "italic": bool(merged.get("italic", defaults["italic"])),
                "underline": bool(merged.get("underline", defaults["underline"])),
                "overstrike": bool(merged.get("overstrike", defaults["overstrike"])),
                "color": merged.get("color", defaults["color"]),
            }
        return result

    def save_settings(self, settings: dict) -> None:
        """Write font settings to user_config and refresh."""
        try:
            from ..config_loader import load_user, save_user
            cfg = load_user()
            cfg["font_settings"] = settings
            save_user(cfg)
        except Exception as e:
            logger.warning("[font_manager] save failed: %s", e)
        self.refresh()

    @property
    def initialized(self) -> bool:
        return self._initialized


# Module-level singleton
font_manager = FontManager()
