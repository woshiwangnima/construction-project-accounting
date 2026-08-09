"""颜色、字体、间距与圆角 tokens 定义（Tk 与 Qt 共享）"""

from ..theme_tokens import (
    DANGER_BG,
    DANGER_FG,
    FONT_FALLBACK,
    INFO_BG,
    INFO_FG,
    STATUS_DONE_BG,
    STATUS_DONE_FG,
    STATUS_EDITING_BG,
    STATUS_EDITING_FG,
    SUCCESS_BG,
    SUCCESS_FG,
    TEXT_PRIMARY,
    TEXT_SECONDARY,
    TEXT_TERTIARY,
    WARNING_BG,
    WARNING_FG,
)

# ── 颜色 ──────────────────────────────────────────────────────────────────────
# Apple 风格系统色板（iOS/macOS 系统色近似）
APP_BG = "#ffffff"

SIDEBAR_BG = "#edf0f4"
SIDEBAR_FG = "#1c1c1e"
SIDEBAR_HOVER = "#e5e5ea"
SIDEBAR_HEADER_BG = "#007aff"
SIDEBAR_HEADER_FG = "#ffffff"
SIDEBAR_SELECTED_BG = "#ffffff"
SIDEBAR_SELECTED_FG = "#007aff"
SIDEBAR_ITEM_BORDER = "#e5e5ea"

ACCENT = "#007aff"
ACCENT_HOVER = "#0071e3"
ACCENT_PRESSED = "#0066d6"
ACCENT_LIGHT = "#ebf5ff"
ACCENT_FOCUS = "#b3d9ff"

DANGER = "#ff3b30"
DANGER_HOVER = "#ff453a"
DANGER_PRESSED = "#d70015"

# 文本层（值来自 theme_tokens）：
#   TEXT_SECONDARY #6e6e73（对 #ffffff 对比度约 5.4:1）
#   TEXT_TERTIARY  #c7c7cc（仅禁用态 / 占位）
BORDER = "#e5e5ea"
SEPARATOR = "#e5e5ea"
HIGHLIGHT_BG = "#ebf5ff"

# 系统语义色
SYSTEM_GREEN = "#34c759"
SYSTEM_RED = "#ff3b30"
SYSTEM_ORANGE = "#ff9500"

# 语义色对（前景 + 浅底，值来自 theme_tokens）：SUCCESS/WARNING/DANGER/INFO
# 项目状态徽章色对：STATUS_EDITING_*（蓝）/ STATUS_DONE_*（绿）

# 已审核行底色（极淡绿，保持可读性，避免饱和色整行冲击）
REVIEW_BG = "#e8f8ee"

# 列表视觉
ROW_HOVER = "#f5f5f7"
ROW_STRIPE = "#fafafc"
TABLE_HEADER_BG = "#f2f2f7"
TABLE_HEADER_FG = "#3a3a3c"

# Icon button colors (sidebar top-level buttons)
ICON_BTN_BG = "#f2f2f7"
ICON_BTN_HOVER = "#e5e5ea"
ICON_BTN_ACTIVE = "#d1d1d6"

# ── 圆角与间距 tokens（Qt 侧主要使用）──────────────────────────────────────────
RADIUS_SM = 6
RADIUS_MD = 8
RADIUS_LG = 10

PAD_XS = 2
PAD_SM = 4
PAD_MD = 6
PAD_LG = 8

GAP_SM = 4
GAP_MD = 8
GAP_LG = 12

# ── 组件语义色（Qt QSS 统一使用）──────────────────────────────────────────────
CARD_BG = "#ffffff"
CARD_BORDER = "#e5e5ea"
BTN_SECONDARY_BG = "#ffffff"
BTN_SECONDARY_HOVER = "#f5f5f7"
SEGMENT_BG = "#f2f2f7"
SEGMENT_SELECTED_BG = "#ffffff"
TOOLTIP_BG = "#1c1c1e"
TOOLTIP_FG = "#ffffff"
MENU_BG = "#ffffff"
MENU_HOVER = "#ebf5ff"
ITEM_SELECTED_BG = "#ebf5ff"
LIST_EMPTY_FG = "#c7c7cc"

# ── 字体 ──────────────────────────────────────────────────────────────────────
FONT_TITLE = ("Microsoft YaHei UI", 22, "bold")
FONT_HEADING = ("Microsoft YaHei UI", 17, "bold")
FONT_SUBHEADING = ("Microsoft YaHei UI", 15, "bold")
FONT_BODY = ("Microsoft YaHei UI", 13)
FONT_BODY_BOLD = ("Microsoft YaHei UI", 14, "bold")
FONT_SMALL = ("Microsoft YaHei UI", 12)
FONT_BUTTON = ("Microsoft YaHei UI", 14, "bold")
FONT_TREE = ("Microsoft YaHei UI", 14)
FONT_TREE_HEADER = ("Microsoft YaHei UI", 14, "bold")
FONT_CALC_BTN = ("Microsoft YaHei UI", 18, "bold")

# ── Qt (PySide6) 侧定义：字体规格与 QSS 生成 ──────────────────────────────────
from dataclasses import dataclass


@dataclass(frozen=True)
class FontSpec:
    """Qt 字体规格：family/size/weight 三元组，与 FONT_* 元组结构一致。"""
    family: str
    size: int
    weight: str = ""

    @classmethod
    def from_tuple(cls, value: tuple) -> "FontSpec":
        return cls(*value)


def build_qss(base_size: int | None = None) -> str:
    """由主题常量生成全局 QSS 样式表（PySide6）。

    统一设计体系：主/次/危险按钮、分段页签、卡片、菜单、列表、
    滚动条、分割条、输入控件与表格；控件细节由各组件按需补充。

    `base_size`：正文基准字号（px），默认读取 app_config 的
    default_font_size。QSS 是 Qt 侧实际生效的字号唯一来源
    （setFont 会被 QSS 的 font-size 覆盖），因此这里跟随配置，
    设置面板调整默认字号即可整体放大/缩小 UI。
    """
    if base_size is None:
        try:
            from ..config_loader import load_app
            base_size = int(load_app().get("default_font_size", 14))
        except Exception:
            base_size = 14
    base_size = max(10, min(30, base_size))
    # 关键角色按 base_size 等比放大，恢复标题/大数字层级
    title_px = max(base_size, round(base_size * 1.57))
    heading_px = max(base_size, round(base_size * 1.2))
    amount_px = max(base_size, round(base_size * 2.0))
    font_family = ", ".join(FONT_FALLBACK)
    return f"""
* {{ outline: none; }}
QWidget {{
    color: {TEXT_PRIMARY};
    font-family: {font_family};
    font-size: {base_size}px;
}}
QLabel#page_title {{
    font-size: {title_px}px;
    font-weight: bold;
}}
QLabel#welcome_title {{
    font-size: {heading_px}px;
    font-weight: bold;
}}
QLabel#amount_value {{
    font-size: {amount_px}px;
    font-weight: bold;
}}
QMainWindow, QDialog {{
    background: {APP_BG};
}}

/* ── 按钮：主 / 次 / 危险 / 扁平 ── */
QPushButton {{
    background: {ACCENT};
    color: white;
    border: 1px solid {ACCENT};
    border-radius: {RADIUS_MD}px;
    padding: 8px 18px;
    min-height: 24px;
    font-weight: bold;
}}
QPushButton:hover {{ background: {ACCENT_HOVER}; border-color: {ACCENT_HOVER}; }}
QPushButton:pressed {{ background: {ACCENT_PRESSED}; border-color: {ACCENT_PRESSED}; }}
QPushButton:disabled {{
    background: #e5e5ea;
    border-color: #e5e5ea;
    color: #a1a1a6;
}}
QPushButton:focus {{ outline: none; border: 1px solid {ACCENT_FOCUS}; }}

QPushButton[secondary="true"] {{
    background: {BTN_SECONDARY_BG};
    color: {TEXT_PRIMARY};
    border: 1px solid {CARD_BORDER};
}}
QPushButton[secondary="true"]:hover {{ background: {BTN_SECONDARY_HOVER}; border-color: #d1d1d6; }}
QPushButton[secondary="true"]:pressed {{ background: {ROW_STRIPE}; }}

QPushButton[danger="true"] {{
    background: {DANGER};
    color: white;
    border-color: {DANGER};
}}
QPushButton[danger="true"]:hover {{ background: {DANGER_HOVER}; border-color: {DANGER_HOVER}; }}
QPushButton[danger="true"]:pressed {{ background: {DANGER_PRESSED}; border-color: {DANGER_PRESSED}; }}

QPushButton[flat="true"] {{
    background: transparent;
    color: {TEXT_SECONDARY};
    border: none;
    font-weight: normal;
    border-radius: {RADIUS_SM}px;
    padding: 4px 8px;
}}
QPushButton[flat="true"]:hover {{
    background: {ROW_HOVER};
    color: {TEXT_PRIMARY};
}}

/* ── 分段页签（tab property）── */
QPushButton[tab="true"] {{
    background: transparent;
    color: {TEXT_SECONDARY};
    border: none;
    border-radius: {RADIUS_SM}px;
    padding: 6px 14px;
    font-weight: normal;
}}
QPushButton[tab="true"]:hover {{
    background: {ROW_HOVER};
    color: {TEXT_PRIMARY};
}}
QPushButton[tab="true"]:checked {{
    background: {SEGMENT_SELECTED_BG};
    color: {ACCENT};
    border: 1px solid {CARD_BORDER};
    font-weight: bold;
}}

/* ── 输入控件 ── */
QLineEdit, QComboBox, QSpinBox, QDoubleSpinBox, QDateEdit, QPlainTextEdit, QTextEdit {{
    background: {APP_BG};
    color: {TEXT_PRIMARY};
    border: 1px solid {BORDER};
    border-radius: {RADIUS_MD}px;
    padding: 6px 10px;
    min-height: 20px;
    selection-background-color: {ACCENT};
    selection-color: white;
}}
QLineEdit:hover, QComboBox:hover, QSpinBox:hover, QDoubleSpinBox:hover, QDateEdit:hover, QPlainTextEdit:hover, QTextEdit:hover {{
    border-color: #b0b0b5;
}}
QLineEdit:focus, QComboBox:focus, QSpinBox:focus, QDoubleSpinBox:focus, QDateEdit:focus, QPlainTextEdit:focus, QTextEdit:focus {{
    border: 1px solid {ACCENT};
    background: #ffffff;
}}
QLineEdit[readOnly="true"] {{
    background: #f2f2f7;
    color: {TEXT_SECONDARY};
}}
QComboBox::drop-down {{
    border: none;
    width: 24px;
}}
QComboBox QAbstractItemView {{
    background: {MENU_BG};
    border: 1px solid {CARD_BORDER};
    border-radius: {RADIUS_MD}px;
    padding: 4px;
    selection-background-color: {MENU_HOVER};
    selection-color: {TEXT_PRIMARY};
    outline: none;
}}
QComboBox QAbstractItemView::item {{
    padding: 6px 10px;
    border-radius: {RADIUS_SM}px;
    min-height: 22px;
}}

/* ── 复选框 / 单选 ── */
QCheckBox, QRadioButton {{
    spacing: 8px;
    color: {TEXT_PRIMARY};
}}
QCheckBox::indicator, QRadioButton::indicator {{
    width: 16px;
    height: 16px;
    border: 1px solid {TEXT_TERTIARY};
    border-radius: 4px;
    background: {APP_BG};
}}
QCheckBox::indicator:hover, QRadioButton::indicator:hover {{
    border-color: {ACCENT};
}}
QCheckBox::indicator:checked {{
    background: {ACCENT};
    border-color: {ACCENT};
}}
QRadioButton::indicator {{ border-radius: 9px; }}
QRadioButton::indicator:checked {{
    background: {ACCENT};
    border-color: {ACCENT};
}}

/* ── 卡片与容器 ── */
QFrame[card="true"], QWidget[card="true"] {{
    background: {CARD_BG};
    border: 1px solid {CARD_BORDER};
    border-radius: {RADIUS_LG}px;
}}

/* ── 状态栏 ── */
QStatusBar {{
    background: {SIDEBAR_BG};
    color: {TEXT_SECONDARY};
    border-top: 1px solid {BORDER};
    font-size: 12px;
    padding: 2px 8px;
}}

/* ── 菜单 ── */
QMenu {{
    background: {MENU_BG};
    color: {TEXT_PRIMARY};
    border: 1px solid {CARD_BORDER};
    border-radius: {RADIUS_MD}px;
    padding: {PAD_SM}px;
}}
QMenu::item {{
    padding: {PAD_MD}px 28px {PAD_MD}px 12px;
    border-radius: {RADIUS_SM}px;
}}
QMenu::item:selected {{ background: {MENU_HOVER}; }}
QMenu::item:disabled {{ color: {TEXT_TERTIARY}; }}
QMenu::separator {{
    height: 1px;
    background: {SEPARATOR};
    margin: {PAD_SM}px 8px;
}}

/* ── 提示 ── */
QToolTip {{
    background: {TOOLTIP_BG};
    color: {TOOLTIP_FG};
    border: none;
    border-radius: {RADIUS_SM}px;
    padding: {PAD_SM}px 8px;
}}
QMessageBox {{ background: {APP_BG}; }}

/* ── 分割条 ── */
QSplitter::handle {{
    background: {BORDER};
}}
QSplitter::handle:hover {{
    background: {ACCENT};
}}
QSplitter::handle:horizontal {{ width: 1px; }}
QSplitter::handle:vertical {{ height: 1px; }}

/* ── 列表 ── */
QListView, QListWidget, QTreeView {{
    background: transparent;
    border: none;
    outline: none;
}}
QListWidget::item, QListView::item {{
    border: none;
    border-radius: {RADIUS_SM}px;
}}
QListWidget::item:hover, QListView::item:hover {{
    background: {ROW_HOVER};
}}
QListWidget::item:selected, QListView::item:selected {{
    background: {ITEM_SELECTED_BG};
    color: {ACCENT};
}}

/* ── 表格 ── */
QTableView {{
    background: {APP_BG};
    alternate-background-color: {ROW_STRIPE};
    border: 1px solid {BORDER};
    border-radius: {RADIUS_MD}px;
    gridline-color: #f0f0f5;
    selection-background-color: {HIGHLIGHT_BG};
    selection-color: {ACCENT};
    outline: none;
}}
QTableView::item {{
    border: none;
    padding: 4px 10px;
    min-height: 42px;
}}
QTableView::item:hover {{ background: {ROW_HOVER}; }}
QTableView::item:selected {{
    background: {HIGHLIGHT_BG};
    color: {ACCENT};
}}
QHeaderView::section {{
    background: {TABLE_HEADER_BG};
    color: {TABLE_HEADER_FG};
    border: none;
    border-bottom: 1px solid {BORDER};
    border-right: 1px solid {SEPARATOR};
    padding: 8px 10px;
    font-weight: bold;
}}
QHeaderView::section:last {{
    border-right: none;
}}
QTableCornerButton::section {{
    background: {TABLE_HEADER_BG};
    border: none;
}}

/* ── 滚动条（细条）── */
QScrollBar:vertical {{
    background: transparent;
    width: 8px;
    margin: 2px;
}}
QScrollBar::handle:vertical {{
    background: {TEXT_TERTIARY};
    border-radius: 4px;
    min-height: 24px;
}}
QScrollBar::handle:vertical:hover {{ background: {TEXT_SECONDARY}; }}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
QScrollBar:horizontal {{
    background: transparent;
    height: 8px;
    margin: 2px;
}}
QScrollBar::handle:horizontal {{
    background: {TEXT_TERTIARY};
    border-radius: 4px;
    min-width: 24px;
}}
QScrollBar::handle:horizontal:hover {{ background: {TEXT_SECONDARY}; }}
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{ width: 0; }}

/* ── 进度条 / 页签（P4 备用）── */
QProgressBar {{
    background: {TABLE_HEADER_BG};
    border: none;
    border-radius: {RADIUS_SM}px;
    text-align: center;
    height: 8px;
}}
QProgressBar::chunk {{
    background: {ACCENT};
    border-radius: {RADIUS_SM}px;
}}
QTabWidget::pane {{
    border: 1px solid {CARD_BORDER};
    border-radius: {RADIUS_MD}px;
    top: -1px;
}}
QTabBar::tab {{
    background: transparent;
    padding: {PAD_MD}px 14px;
    border: none;
    border-radius: {RADIUS_SM}px;
}}
QTabBar::tab:selected {{
    background: {SEGMENT_SELECTED_BG};
    color: {ACCENT};
    font-weight: bold;
}}
QTabBar::tab:hover {{
    background: {ROW_HOVER};
}}
"""
