"""纯语义颜色 / 字体 token（不依赖 Qt / Tk 任何模块）。

供 src/gui/theme.py（Tk 与 Qt 共享色板）与 src/project_status.py 等
非 GUI 模块引用，避免领域层反向依赖 GUI。

── 色板约定（2026-09-18 起：工程记账暖中性色）──────────────────────────────
1. **一套中性色**：暖灰（warm gray），暖白底 #faf9f7 → 暖黑字 #1f1e1d。
   历史上 Apple 灰（#1c1c1e/#e5e5ea）、Tailwind 灰（#374151/#d1d5db）并存，
   已统一收回此处。新增任何硬编码 hex 之前先看这里有没有可用 token。
2. **一个强调色**：赤陶橙系（单色相不同明度），不再有蓝 / 青第二色相。
3. **语义色降饱和**：成功=墨绿、警告=暖褐、危险=砖红，全部低饱和暖调，
   只在真正需要语义区分处使用，不用于装饰。
4. **对比度底线**：正文组合 ≥ 4.5:1（原 status_badge 的「中年用户可读性」
   要求仍然有效）。改值时必须重算，不能凭眼睛看着差不多就换。
"""

# ── 文本层（暖灰阶）─────────────────────────────────────────────────────────
# #1f1e1d on #ffffff ≈ 15.9:1；on #faf9f7 ≈ 15.2:1
TEXT_PRIMARY = "#1f1e1d"
# 次要文本：#6b6862 on #ffffff ≈ 5.4:1，on #faf9f7 ≈ 5.1:1
TEXT_SECONDARY = "#6b6862"
# 三级文本：仅用于禁用态 / 占位符 / 滚动条滑块
TEXT_TERTIARY = "#a8a49c"

# ── 语义色对（前景 + 浅底成对，命名沿用 *_BG 后缀风格）──────────────────────
# 前景对白底对比度均 ≥ 6:1，浅底只做极淡的区块区分。
SUCCESS_FG = "#3f6b4a"  # 墨绿，6.1:1
SUCCESS_BG = "#eaf1e9"

WARNING_FG = "#8a5a1a"  # 暖褐，6.2:1
WARNING_BG = "#fbf1de"

DANGER_FG = "#a63a2e"  # 砖红，6.4:1
DANGER_BG = "#faeceb"

# 信息态并入强调色系，避免为非关键状态引入第二种高辨识度色相
INFO_FG = "#8f4522"  # 6.9:1
INFO_BG = "#fbf1ec"

# ── 项目状态徽章色对 ────────────────────────────────────────────────────────
STATUS_EDITING_FG = INFO_FG  # 编辑中：赤陶
STATUS_EDITING_BG = INFO_BG
STATUS_DONE_FG = SUCCESS_FG  # 已完成：墨绿
STATUS_DONE_BG = SUCCESS_BG

# ── 字体回退链（Qt QSS font-family / 其他支持列表字体的场景）─────────────────
FONT_FALLBACK = (
  "Microsoft YaHei UI",
  "Microsoft YaHei",
  "PingFang SC",
  "Segoe UI",
  "sans-serif",
)
