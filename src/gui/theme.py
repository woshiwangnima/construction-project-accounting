"""颜色、字体、间距与圆角 tokens 定义（Tk 与 Qt 共享）"""

from dataclasses import dataclass

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

# 这些 token 由本模块继续作为公共主题 API 导出。
_TOKEN_EXPORTS = (
    DANGER_BG,
    DANGER_FG,
    INFO_BG,
    INFO_FG,
    STATUS_DONE_BG,
    STATUS_DONE_FG,
    STATUS_EDITING_BG,
    STATUS_EDITING_FG,
    SUCCESS_BG,
    SUCCESS_FG,
    WARNING_BG,
    WARNING_FG,
)

# ── 颜色 ──────────────────────────────────────────────────────────────────────
# 工程记账中性色板：暖灰提供结构，赤陶色只用于少量关键强调。
# 规则见 src/theme_tokens.py 顶部注释——新增硬编码 hex 之前先查这里。
APP_BG = "#faf9f7"  # 页面底：暖白，不是纯白

# 文本层：TEXT_PRIMARY / TEXT_SECONDARY / TEXT_TERTIARY 来自 theme_tokens。
# TEXT_MUTED 比 secondary 弱一档但仍 ≥4.5:1，用于次要正文、未选中标记一类
# 不能太浅的地方（TEXT_TERTIARY 只有 2.5:1，那些场合不够读）。
TEXT_MUTED = "#757268"

# 强调色（赤陶橙系，单色相不同明度）
# ACCENT 对白字 ≈ 4.8:1（按钮）；ACCENT_TEXT 更深，用于强调文字 ≈ 6.9:1
ACCENT = "#b5572f"
ACCENT_HOVER = "#9c4826"
ACCENT_PRESSED = "#863b1d"
ACCENT_TEXT = "#8f4522"
ACCENT_LIGHT = "#f7e9e1"  # 极浅赤陶底：选中行 / 菜单 hover
ACCENT_FOCUS = "#dfa98c"

DANGER = "#b0463a"
DANGER_HOVER = "#9a382e"
DANGER_PRESSED = "#822b23"

# 边框 / 分隔（暖灰，比纯灰更贴暖白底）
BORDER = "#e8e5df"
BORDER_STRONG = "#cdc9c0"  # hover / 需要强调的边框
SEPARATOR = "#edeae4"
SURFACE_SUNKEN = "#f4f2ed"  # 只读输入框 / 内嵌凹槽面
GRIDLINE = "#efece7"  # 表格网格线
HIGHLIGHT_BG = ACCENT_LIGHT

# 系统语义色（低饱和暖调，仅用于真正需要语义区分处）
SYSTEM_GREEN = "#4a7a55"
SYSTEM_RED = "#b0463a"
SYSTEM_ORANGE = "#a06a2c"

# 语义色对（前景 + 浅底，值来自 theme_tokens）：SUCCESS/WARNING/DANGER/INFO
# 项目状态徽章色对：STATUS_EDITING_*（赤陶）/ STATUS_DONE_*（墨绿）

# 已审核行底色（极淡绿，保持可读性，避免饱和色整行冲击）
REVIEW_BG = "#eef3ec"

# 侧栏（暖灰底，不再用蓝色横幅）
SIDEBAR_BG = "#f4f2ed"
SIDEBAR_FG = "#1f1e1d"
SIDEBAR_HOVER = "#eceae4"
SIDEBAR_HEADER_BG = "#f4f2ed"
SIDEBAR_HEADER_FG = "#1f1e1d"
SIDEBAR_SELECTED_BG = "#ffffff"
SIDEBAR_SELECTED_FG = ACCENT_TEXT
SIDEBAR_ITEM_BORDER = "#e8e5df"

# 列表视觉
ROW_HOVER = "#f4f2ed"
ROW_STRIPE = "#fcfbf9"
TABLE_HEADER_BG = "#f4f2ed"
TABLE_HEADER_FG = "#57544e"

# Icon button colors (sidebar top-level buttons)
ICON_BTN_BG = "#f4f2ed"
ICON_BTN_HOVER = "#eceae4"
ICON_BTN_ACTIVE = "#dedbd3"

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
CARD_BORDER = "#e8e5df"
BTN_SECONDARY_BG = "#ffffff"
BTN_SECONDARY_HOVER = "#f4f2ed"
BTN_DISABLED_BG = "#f0eee9"
BTN_DISABLED_FG = "#a8a49c"
SEGMENT_BG = "#f0eee9"
SEGMENT_SELECTED_BG = "#ffffff"
# Tooltip 必须固定为高对比度深底浅字。Windows 原生样式与 qfluentwidgets
# 可能分别接管背景或文字，因此 QSS 与 QApplication palette 必须同时设置。
TOOLTIP_BG = TEXT_PRIMARY
TOOLTIP_FG = CARD_BG
TOOLTIP_QSS = (
    f"QToolTip {{ background-color: {TOOLTIP_BG}; color: {TOOLTIP_FG};"
    f" border: 1px solid {BORDER_STRONG}; border-radius: {RADIUS_SM}px;"
    f" padding: {PAD_SM}px 8px; }}"
)
MENU_BG = "#ffffff"
MENU_HOVER = ACCENT_LIGHT
ITEM_SELECTED_BG = ACCENT_LIGHT
LIST_EMPTY_FG = "#a8a49c"

# ── 字号 ──────────────────────────────────────────────────────────────────────
# 倍率表是**全库唯一真源**：QSS（build_qss）与 QFont（font_manager）都从这里取。
# 有效字号 = round(默认字号 × 倍率)，单位 px。
#
# 为什么必须统一成 px：QSS 侧写的是 font-size: Npx，若另一条通道改用
# setPointSize，表格单元格（走 model 的 FontRole）会比界面其它文字大约三分之一，
# 同一屏里就会看到两种大小的正文。
FONT_SIZE_MULTIPLIERS = {
    "icon_btn": 1.0,
    "dialog_btn": 1.0,
    "entry_item": 1.0,
    "button": 1.0,
    "calc_btn": 1.29,
    "title": 1.57,
    "heading": 1.2,
    "subheading": 1.07,
    "body": 1.0,
    "body_bold": 1.0,
    "tree": 1.0,
    "tree_header": 1.0,
    "small": 0.86,
    "amount": 2.0,
}

DEFAULT_FONT_SIZE = 14
FONT_FAMILY = FONT_FALLBACK[0]


def clamp_base_font_size(size) -> int:
    """把默认字号收进制定的可用区间（px）；非法值回退 DEFAULT_FONT_SIZE。"""
    try:
        value = int(size)
    except (TypeError, ValueError):
        value = DEFAULT_FONT_SIZE
    return max(10, min(30, value))


def base_font_size() -> int:
    """当前正文基准字号（px），读 app_config 的 default_font_size。"""
    try:
        from ..config_loader import load_app

        return clamp_base_font_size(
            load_app().get("default_font_size", DEFAULT_FONT_SIZE)
        )
    except Exception:
        return DEFAULT_FONT_SIZE


def font_px(role: str = "body", base_size: int | None = None) -> int:
    """按角色返回实际字号（px）。

    组件里不要再写 ``font-size: 14px`` 这类字面量——那等于脱离配置，
    用户在设置里改默认字号时它纹丝不动。用::

        f"font-size: {font_px('subheading')}px;"

    ``base_size`` 用于在一次渲染内复用同一基准（build_qss 传参用），
    省略则实时读配置。
    """
    base = base_font_size() if base_size is None else clamp_base_font_size(base_size)
    return max(8, round(base * FONT_SIZE_MULTIPLIERS.get(role, 1.0)))


def label_col_width(chars: int = 6, role: str = "body") -> int:
    """表单里「标签列」的固定宽度（px），按最长标签字数随字号缩放。

    这类标签列是为了让多行控件左边缘对齐才固定宽度的，但**不能写死**：
    原先值 90px，默认字号调到 20 时「已审核行颜色」需要约 120px，
    结果被截成「已审核行颜…」。90 是给老字号的保底下限。
    """
    return max(90, round(font_px(role) * chars))


# 旧 Tk 时代的 (family, size, weight) 元组常量。仍保留，但**按默认字号派生**，
# 保证不会与 font_px 分叉——这里手写的 FONT_BODY=13 曾与 font_manager 的
# body=14 长期打架，就是"同一屏两种正文字号"的来源之一。
# 新代码请直接用 font_px() 或 font_manager.get(role)。
FONT_TITLE = (FONT_FAMILY, font_px("title", DEFAULT_FONT_SIZE), "bold")
FONT_HEADING = (FONT_FAMILY, font_px("heading", DEFAULT_FONT_SIZE), "bold")
FONT_SUBHEADING = (FONT_FAMILY, font_px("subheading", DEFAULT_FONT_SIZE), "bold")
FONT_BODY = (FONT_FAMILY, font_px("body", DEFAULT_FONT_SIZE), "")
FONT_BODY_BOLD = (FONT_FAMILY, font_px("body_bold", DEFAULT_FONT_SIZE), "bold")
FONT_SMALL = (FONT_FAMILY, font_px("small", DEFAULT_FONT_SIZE), "")
FONT_BUTTON = (FONT_FAMILY, font_px("button", DEFAULT_FONT_SIZE), "bold")
FONT_TREE = (FONT_FAMILY, font_px("tree", DEFAULT_FONT_SIZE), "")
FONT_TREE_HEADER = (FONT_FAMILY, font_px("tree_header", DEFAULT_FONT_SIZE), "bold")
FONT_CALC_BTN = (FONT_FAMILY, font_px("calc_btn", DEFAULT_FONT_SIZE), "bold")


# ── Qt (PySide6) 侧定义：字体规格与 QSS 生成 ──────────────────────────────────
@dataclass(frozen=True)
class FontSpec:
    """Qt 字体规格：family/size/weight 三元组，与 FONT_* 元组结构一致。"""

    family: str
    size: int
    weight: str = ""

    @classmethod
    def from_tuple(cls, value: tuple) -> "FontSpec":
        return cls(*value)


def apply_tooltip_palette(app) -> None:
    """同步 Qt 原生 Tooltip 调色板，防止 QSS 与平台主题各应用一半。"""
    from PySide6.QtGui import QColor, QPalette

    palette = app.palette()
    palette.setColor(QPalette.ColorRole.ToolTipBase, QColor(TOOLTIP_BG))
    palette.setColor(QPalette.ColorRole.ToolTipText, QColor(TOOLTIP_FG))
    app.setPalette(palette)


def build_qss(base_size: int | None = None) -> str:
    """由主题常量生成全局 QSS 样式表（PySide6）。

    统一设计体系：主/次/危险按钮、分段页签、卡片、菜单、列表、
    滚动条、分割条、输入控件与表格；控件细节由各组件按需补充。

    `base_size`：正文基准字号（px），默认读取 app_config 的
    default_font_size。QSS 是 Qt 侧实际生效的字号唯一来源
    （setFont 会被 QSS 的 font-size 覆盖），因此这里跟随配置，
    设置面板调整默认字号即可整体放大/缩小 UI。
    """
    base_size = (
        base_font_size() if base_size is None else clamp_base_font_size(base_size)
    )
    # 平台主题和 QSS 可能分别接管 Tooltip 的底色与文字色；构建全局样式时
    # 同步 palette，确保说明文字始终使用同一组高对比度颜色。
    from PySide6.QtWidgets import QApplication

    app = QApplication.instance()
    if app is not None:
        apply_tooltip_palette(app)
    # 角色字号统一由倍率表推导（与 font_manager 同源），不在 QSS 里写死任何 px
    title_px = font_px("title", base_size)
    heading_px = font_px("heading", base_size)
    amount_px = font_px("amount", base_size)
    small_px = font_px("small", base_size)
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
    background: {BTN_DISABLED_BG};
    border-color: {BTN_DISABLED_BG};
    color: {BTN_DISABLED_FG};
}}
QPushButton:focus {{ outline: none; border: 1px solid {ACCENT_FOCUS}; }}

QPushButton[secondary="true"] {{
    background: {BTN_SECONDARY_BG};
    color: {TEXT_PRIMARY};
    border: 1px solid {CARD_BORDER};
}}
QPushButton[secondary="true"]:hover {{ background: {BTN_SECONDARY_HOVER}; border-color: {BORDER_STRONG}; }}
QPushButton[secondary="true"]:pressed {{ background: {ROW_STRIPE}; }}

QPushButton[danger="true"] {{
    background: {DANGER};
    color: white;
    border-color: {DANGER};
}}
QPushButton[danger="true"]:hover {{ background: {DANGER_HOVER}; border-color: {DANGER_HOVER}; }}
QPushButton[danger="true"]:pressed {{ background: {DANGER_PRESSED}; border-color: {DANGER_PRESSED}; }}

/* 禁用态必须显式覆盖 secondary/danger：属性选择器优先级高于 :disabled 伪类，
   否则白字会压在 :disabled 的浅灰底上，按钮文字直接消失。 */
QPushButton:disabled,
QPushButton[secondary="true"]:disabled,
QPushButton[danger="true"]:disabled {{
    background: {BTN_DISABLED_BG};
    border-color: {BTN_DISABLED_BG};
    color: {BTN_DISABLED_FG};
}}

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

/* ── 页面导航与表格视图切换：中性色承担结构，强调色只标记主导航 ── */
QPushButton[navigation="true"], QPushButton[viewMode="true"] {{
    background: transparent;
    color: {TEXT_SECONDARY};
    border: none;
    border-radius: {RADIUS_SM}px;
    padding: 6px 12px;
    font-weight: normal;
}}
QPushButton[navigation="true"]:hover, QPushButton[viewMode="true"]:hover {{
    background: {ROW_HOVER};
    color: {TEXT_PRIMARY};
}}
QPushButton[navigation="true"]:checked {{
    background: {SEGMENT_BG};
    color: {ACCENT_TEXT};
    border: none;
    font-weight: bold;
}}
QPushButton[viewMode="true"]:checked {{
    background: {SEGMENT_SELECTED_BG};
    color: {TEXT_PRIMARY};
    border: none;
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
    border-color: {BORDER_STRONG};
}}
QLineEdit:focus, QComboBox:focus, QSpinBox:focus, QDoubleSpinBox:focus, QDateEdit:focus, QPlainTextEdit:focus, QTextEdit:focus {{
    border: 1px solid {ACCENT};
    background: #ffffff;
}}
QLineEdit[readOnly="true"] {{
    background: {SURFACE_SUNKEN};
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
    font-size: {small_px}px;
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
{TOOLTIP_QSS}
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
    gridline-color: {GRIDLINE};
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

/* ── 滑条（原生 QSlider 在 Win11 会用系统强调色蓝，必须显式覆盖）── */
QSlider::groove:horizontal {{
    height: 4px;
    background: {SURFACE_SUNKEN};
    border-radius: 2px;
}}
QSlider::sub-page:horizontal {{
    background: {ACCENT};
    border-radius: 2px;
}}
QSlider::handle:horizontal {{
    width: 16px;
    height: 16px;
    margin: -6px 0;
    border-radius: 8px;
    background: {CARD_BG};
    border: 2px solid {ACCENT};
}}
QSlider::handle:horizontal:hover {{ border-color: {ACCENT_HOVER}; }}
QSlider::groove:vertical {{
    width: 4px;
    background: {SURFACE_SUNKEN};
    border-radius: 2px;
}}
QSlider::add-page:vertical {{
    background: {ACCENT};
    border-radius: 2px;
}}
QSlider::handle:vertical {{
    height: 16px;
    width: 16px;
    margin: 0 -6px;
    border-radius: 8px;
    background: {CARD_BG};
    border: 2px solid {ACCENT};
}}

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
