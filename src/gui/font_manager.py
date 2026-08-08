"""FontManager: dynamic font resolution with live-update support.

Usage:
    from .font_manager import font_manager

    # After Tk root is created (main_window.py):
    font_manager.init(root)

    # In widgets:
    font=font_manager.get("body")          # → tk.font.Font object
    fg=font_manager.get_color("body")      # → theme.TEXT_PRIMARY

    # Settings panel triggers refresh after save:
    font_manager.refresh()
"""

import tkinter as tk
import tkinter.font as tkfont

from ..logger import logger
from .theme import TEXT_PRIMARY, TEXT_SECONDARY

# ── 角色定义 ──────────────────────────────────────────────────────────────────
# 每个角色对应一组 theme.py 常量，可独立配置字体族/字号/加粗/斜体/下划线/删除线/颜色。

ROLE_KEYS = ("icon_btn", "dialog_btn", "entry_item", "button", "calc_btn",
             "title", "heading", "subheading",
             "body", "body_bold",
             "tree", "tree_header", "small")

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
}

# 5 个分组（用于设置面板 UI 分区）
ROLE_GROUPS = [
    ("按钮类", ("icon_btn", "dialog_btn", "entry_item", "button", "calc_btn")),
    ("标题类", ("title", "heading", "subheading")),
    ("正文类", ("body", "body_bold")),
    ("表格类", ("tree", "tree_header")),
    ("辅助", ("small",)),
]

# 字号乘数：effective_size = round(default_font_size * multiplier)
_ROLE_SIZE_MULTIPLIERS = {
    "icon_btn":    1.07,
    "dialog_btn":  0.8,
    "entry_item":  0.93,
    "button":      0.93,
    "calc_btn":    1.29,
    "title":       1.57,
    "heading":     1.14,
    "subheading":  1.0,
    "body":        0.93,
    "body_bold":   0.93,
    "tree":        0.93,
    "tree_header": 0.93,
    "small":       0.79,
}

_DEFAULT_FONT_SIZE = 14

_ROLE_DEFAULTS = {
    "icon_btn":    {"family": "Microsoft YaHei UI", "size": 15, "bold": True,  "italic": False, "underline": False, "overstrike": False, "color": TEXT_PRIMARY},
    "dialog_btn":  {"family": "Microsoft YaHei UI", "size": 11, "bold": True,  "italic": False, "underline": False, "overstrike": False, "color": TEXT_PRIMARY},
    "entry_item":  {"family": "Microsoft YaHei UI", "size": 13, "bold": True,  "italic": False, "underline": False, "overstrike": False, "color": TEXT_PRIMARY},
    "title":       {"family": "Microsoft YaHei UI", "size": 22, "bold": True,  "italic": False, "underline": False, "overstrike": False, "color": TEXT_PRIMARY},
    "heading":     {"family": "Microsoft YaHei UI", "size": 16, "bold": True,  "italic": False, "underline": False, "overstrike": False, "color": TEXT_PRIMARY},
    "subheading":  {"family": "Microsoft YaHei UI", "size": 14, "bold": True,  "italic": False, "underline": False, "overstrike": False, "color": TEXT_PRIMARY},
    "body":        {"family": "Microsoft YaHei UI", "size": 13, "bold": False, "italic": False, "underline": False, "overstrike": False, "color": TEXT_PRIMARY},
    "body_bold":   {"family": "Microsoft YaHei UI", "size": 13, "bold": True,  "italic": False, "underline": False, "overstrike": False, "color": TEXT_PRIMARY},
    "button":      {"family": "Microsoft YaHei UI", "size": 13, "bold": True,  "italic": False, "underline": False, "overstrike": False, "color": "#ffffff"},
    "calc_btn":    {"family": "Microsoft YaHei UI", "size": 18, "bold": True,  "italic": False, "underline": False, "overstrike": False, "color": TEXT_PRIMARY},
    "tree":        {"family": "Microsoft YaHei UI", "size": 13, "bold": False, "italic": False, "underline": False, "overstrike": False, "color": TEXT_PRIMARY},
    "tree_header": {"family": "Microsoft YaHei UI", "size": 13, "bold": True,  "italic": False, "underline": False, "overstrike": False, "color": TEXT_PRIMARY},
    "small":       {"family": "Microsoft YaHei UI", "size": 11, "bold": False, "italic": False, "underline": False, "overstrike": False, "color": TEXT_SECONDARY},
}


def _cfg_to_font_kwargs(cfg: dict) -> dict:
    """Convert a user_config font entry to tk.font.Font kwargs."""
    return {
        "family": cfg.get("family", "Microsoft YaHei UI"),
        "size": int(cfg.get("size", 14)),
        "weight": "bold" if cfg.get("bold") else "normal",
        "slant": "italic" if cfg.get("italic") else "roman",
        "underline": 1 if cfg.get("underline") else 0,
        "overstrike": 1 if cfg.get("overstrike") else 0,
    }


class FontManager:
    """Singleton font manager — creates and manages tk.font.Font named-font objects."""

    def __init__(self):
        self._root: tk.Tk | None = None
        self._fonts: dict[str, tkfont.Font] = {}
        self._colors: dict[str, str] = {}
        self._initialized = False

    def init(self, root: tk.Tk) -> None:
        """Initialize font objects. MUST be called after Tk root is created."""
        if self._initialized:
            return
        self._root = root
        self._build_fonts()
        self._initialized = True
        logger.debug("[font_manager] initialized %d roles", len(self._fonts))

    def _build_fonts(self) -> None:
        """Build (or rebuild) tk.font.Font objects from config + defaults.

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
            font_kwargs = _cfg_to_font_kwargs(merged)
            color = merged.get("color", defaults["color"])

            name = f"CPA_{role}"
            if role in self._fonts:
                self._fonts[role].configure(**font_kwargs)
                self._colors[role] = color
            else:
                self._fonts[role] = tkfont.Font(root=self._root, name=name, **font_kwargs)
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

    def get(self, role: str) -> tkfont.Font:
        """Return the tk.font.Font object for a role. Falls back to 'body' if unknown."""
        if not self._initialized:
            # Before init, return a static tuple-like fallback
            return tkfont.Font(family="Microsoft YaHei UI", size=14)
        return self._fonts.get(role, self._fonts.get("body"))

    def get_color(self, role: str) -> str:
        """Return the configured color for a role."""
        if not self._initialized:
            return _ROLE_DEFAULTS.get(role, _ROLE_DEFAULTS["body"])["color"]
        return self._colors.get(role, _ROLE_DEFAULTS.get(role, _ROLE_DEFAULTS["body"])["color"])

    def get_tuple(self, role: str) -> tuple:
        """Return (family, size) or (family, size, 'bold') tuple — for places that need a tuple."""
        f = self.get(role)
        family = f.cget("family")
        size = f.cget("size")
        weight = f.cget("weight")
        if weight == "bold":
            return (family, size, "bold")
        return (family, size)

    def refresh(self) -> None:
        """Re-read user_config and update all font objects in-place.

        Since widgets hold a reference to the same tk.font.Font object,
        calling .configure() on it automatically updates all widgets.
        Also re-applies ttk styles.
        """
        if not self._initialized:
            return
        self._build_fonts()
        self._apply_ttk_styles()
        logger.debug("[font_manager] refreshed %d roles", len(self._fonts))

    def _apply_ttk_styles(self) -> None:
        """Re-configure ttk styles to use updated fonts."""
        try:
            from .ttk_theme import apply_ttk_theme
            apply_ttk_theme()
        except Exception as e:
            logger.warning("[font_manager] ttk style update failed: %s", e)

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
