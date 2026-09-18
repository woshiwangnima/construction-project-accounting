"""全局图标定义（qtawesome / Phosphor 线性图标）。

为什么不用 emoji
----------------
彩色 emoji 由系统字体渲染成**多色字形**，与暖灰简约界面直接冲突——
而且不同 Windows 版本字形不一致，缺字时退化成方块或黑白线稿。
矢量图标单色可控、随主题色走，是替换 emoji 的唯一真源。

为什么用 ph.*（Phosphor）而不是 fa5r.*
--------------------------------------
本仓库装的 qtawesome 1.4.2 **只打包了 fa5 / fa5s / fa6 / fa6s，没有 regular
变体**（``qta._instance().charmap`` 里查不到 ``fa5r``），一旦 QApplication
起来就会抛 ``Invalid font prefix "fa5r"``。fa5s 是实心块，视觉重量大。
Phosphor 默认变体就是细线描边（另有 ``-bold`` / ``-fill`` / ``-thin``），
约 4470 个图标，是这里唯一够用的线性字库。

用法
----
::

    from .icons import icon, ICON_SETTINGS
    btn.setIcon(icon(ICON_SETTINGS))
    btn.setIconSize(QSize(16, 16))

新增图标时：只在这里加常量，不要在业务模块里硬写 ``"ph.xxx"`` 字符串；
改字库前缀前先确认 ``charmap`` 里有它（见上）。
"""
from PySide6.QtGui import QIcon

from qtawesome import icon as _qta_icon

from ..theme import TEXT_SECONDARY

# ── 图标名常量（ph.* = Phosphor 默认变体，细线描边）────────────────────────
# 侧栏
ICON_IMPORT = "ph.upload"
ICON_EXPORT = "ph.download"
ICON_SETTINGS = "ph.gear"
ICON_SEARCH = "ph.magnifying-glass"
ICON_PLUS = "ph.plus"
ICON_TRASH = "ph.trash"
ICON_EDIT = "ph.pencil-simple"
ICON_ELLIPSIS = "ph.dots-three"
ICON_FOLDER = "ph.folder-open"
ICON_FOLDER_PLUS = "ph.folder-plus"
ICON_ERASER = "ph.eraser"
ICON_COLUMNS = "ph.columns"
ICON_PIN = "ph.push-pin"
ICON_COLLAPSE = "ph.caret-double-left"
ICON_EXPAND = "ph.caret-double-right"
ICON_CHEVRON_LEFT = "ph.caret-left"
ICON_CHEVRON_RIGHT = "ph.caret-right"

# 页面 / 视图
ICON_BILL = "ph.receipt"
ICON_WORKER = "ph.wrench"          # 施工工种；Phosphor 没有 hard-hat
ICON_PRICE = "ph.tag"
ICON_CALC = "ph.calculator"
ICON_DATABASE = "ph.database"
ICON_LAYERS = "ph.stack"
ICON_LIST = "ph.list"
ICON_TABLE = "ph.table"
ICON_VIEW = "ph.eye"
ICON_FILTER = "ph.funnel"
ICON_SORT = "ph.arrows-down-up"
ICON_STREAM = "ph.list-dashes"

# 状态 / 反馈
ICON_CHECK = "ph.check-circle"
ICON_CHECK_SQUARE = "ph.check-square"
ICON_SQUARE = "ph.square"
ICON_WARNING = "ph.warning"
ICON_INFO = "ph.info"
ICON_QUESTION = "ph.question"
ICON_CLOCK = "ph.hourglass"
ICON_SYNC = "ph.arrows-clockwise"
ICON_UNDO = "ph.arrow-counter-clockwise"
ICON_SAVE = "ph.floppy-disk"
ICON_HISTORY = "ph.clock-counter-clockwise"
ICON_LIGHTBULB = "ph.lightbulb"

# 编辑
ICON_COPY = "ph.copy"
ICON_PASTE = "ph.clipboard-text"
ICON_MOVE_UP = "ph.arrow-up"
ICON_MOVE_DOWN = "ph.arrow-down"
ICON_TIMES = "ph.x"
ICON_SLIDERS = "ph.sliders"

# 导出 / 外观
ICON_IMAGE = "ph.image"
ICON_PALETTE = "ph.palette"
ICON_CALENDAR = "ph.calendar"

# 设置面板
ICON_FONT = "ph.text-aa"
ICON_KEYBOARD = "ph.keyboard"
ICON_BELL = "ph.bell"
ICON_MIC = "ph.microphone"
ICON_VOLUME = "ph.speaker-high"
ICON_PLAY = "ph.play"
ICON_TOOLS = "ph.gauge"

# 默认图标色：中性次要灰。语义场合（警告 / 成功 / 危险）由调用方显式传色。
DEFAULT_COLOR = TEXT_SECONDARY


def icon(name: str, color: str | None = None) -> QIcon:
    """按名字取线性图标。

    `color` 省略时用 `DEFAULT_COLOR`（中性灰）。语义场合请显式传
    `theme.SYSTEM_RED` / `SYSTEM_GREEN` 等，不要就地硬写 hex。
    """
    return _qta_icon(name, color=color or DEFAULT_COLOR)
