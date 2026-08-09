"""纯语义颜色 / 字体 token（不依赖 Qt / Tk 任何模块）。

供 src/gui/theme.py（Tk 与 Qt 共享色板）与 src/project_status.py 等
非 GUI 模块引用，避免领域层反向依赖 GUI。
"""

# ── 文本层 ──────────────────────────────────────────────────────────────────
TEXT_PRIMARY = "#1c1c1e"
# 次要文本：#6e6e73 对 #ffffff 背景对比度约 5.4:1
TEXT_SECONDARY = "#6e6e73"
# 三级文本：仅用于禁用态 / 占位符
TEXT_TERTIARY = "#c7c7cc"

# ── 语义色对（前景 + 浅底成对，命名沿用 *_BG 后缀风格）──────────────────────
SUCCESS_FG = "#1f7a3d"
SUCCESS_BG = "#e8f8ee"

WARNING_FG = "#b25000"
WARNING_BG = "#fff4e5"

DANGER_FG = "#d70015"
DANGER_BG = "#ffeceb"

INFO_FG = "#0060df"
INFO_BG = "#ebf5ff"

# ── 项目状态徽章色对 ────────────────────────────────────────────────────────
STATUS_EDITING_FG = INFO_FG  # 编辑中：蓝
STATUS_EDITING_BG = INFO_BG
STATUS_DONE_FG = SUCCESS_FG  # 已完成：绿
STATUS_DONE_BG = SUCCESS_BG

# ── 字体回退链（Qt QSS font-family / 其他支持列表字体的场景）─────────────────
FONT_FALLBACK = (
    "Microsoft YaHei UI",
    "Microsoft YaHei",
    "PingFang SC",
    "Segoe UI",
    "sans-serif",
)
