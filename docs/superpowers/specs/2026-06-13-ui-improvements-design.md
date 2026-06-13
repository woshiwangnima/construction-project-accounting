# UI 改进设计方案

## 概述

对施工项目记账 Tkinter 桌面应用进行 7 项 UI/UX 改进，涉及滚动组件抽象、图标修复、面板可拖动、头部精简、超链接、Tooltip 轮播、按钮布局优化。

---

## 1. ScrollableFrame — 统一的可滚动容器组件

### 文件

`src/gui/widgets/scrollable_frame.py`

### 接口

```python
class ScrollableFrame(tk.Frame):
    def __init__(
        self,
        parent,
        auto_hide_ms: int | None = None,   # None=常驻, >0=超时隐藏
        scroll_step: int = 3,
        bg: str = APP_BG,
    )
```

### 行为

- 内部布局：`ttk.Scrollbar`（右侧） + `tk.Canvas`（左，fill）
- 鼠标滚轮（`<MouseWheel>` / `<Button-4>` / `<Button-5>`）→ 滚动
- 方向键（`<Up>` / `<Down>`）→ 滚动
- 右侧滚动条拖动滑块 → 原生支持
- `auto_hide_ms=None`：滚动条常驻显示
- `auto_hide_ms>0`：
  - 滚动发生时立即显示滚动条，重置隐藏计时器
  - 计时器超时后 `scrollbar.pack_forget()` 隐藏滚动条
  - 内容未超出视口时滚动条始终隐藏
- 支持 `.bind()` 直接绑到内部 canvas 或 frame，代理到外部

### 替换位置

| 位置 | 文件 | 行号 |
|------|------|------|
| 项目列表 | `sidebar.py` | 85-101 |
| 分类列表 | `content.py` | 1096-1105 |
| 编辑账单对话框 | `edit_bill.py` | 91-105 |
| 编辑工作项目对话框 | `edit_trade.py` | 54-68 |
| 导出图片设置面板 | `export_panel.py` | 201-219 |
| 基础设置面板 | `basic_panel.py` | 新增（当前不可滚动） |
| 语音播报面板 | `voice_panel.py` | 新增（当前不可滚动） |
| 关于面板 | `about_panel.py` | 新增（当前不可滚动） |
| 通用 `_make_scrollable()` | `widgets/__init__.py` | 13-24（替换实现） |

### Settings 面板统一

为基础设置 / 语音播报 / 关于面板新增滚动支持：在 `_build()` 中创建 `ScrollableFrame`，将原有内容放入其内框。

---

## 2. 修复编辑羽毛笔图标 Win10 兼容

当前 `\U0001fab6`（🪶）在 Win10 字体不支持，渲染为空白框。

### 替换

两处均改为 `\U0001f589\ufe0f`（🖉），追加 `\ufe0f` emoji 变体选择器，与右键菜单图标风格一致。

| 文件 | 行号 | 旧值 | 新值 |
|------|------|------|------|
| `content.py` | 620 | `"\U0001fab6"` | `"\U0001f589\ufe0f"` |
| `content.py` | 1137 | `"\U0001fab6"` | `"\U0001f589\ufe0f"` |

---

## 3. 侧边栏 / 分类列表宽度可调整

### 可拖动分隔条组件

`src/gui/widgets/draggable_splitter.py`

```python
class DraggableSplitter(tk.Frame):
    def __init__(self, parent, target, min_width=200, max_width=500,
                 on_resize=None, default_width=320)
```

- 宽度 6px，`cursor="sb_h_double_arrow"`
- `<Button-1>` 按下开始拖动 → `<B1-Motion>` 调整 `target` 宽度
- `<ButtonRelease-1>` 释放 → 回调 `on_resize(width)` 触发保存

### 项目列表侧边栏

- `sidebar.py`：`width=320` → 可拖动
- `main_window.py`：在 sidebar 右侧插入 `DraggableSplitter` 绑定到 sidebar
- 顶部按钮 / 搜索框 / 底部按钮通过 `pack(fill=tk.X)` 自动适配

### 分类列表

- `content.py` `left_frame(width=220)` → 可拖动
- 在 `main_pane` 的 PanedWindow 中左侧分类面板添加分隔条

### 宽度保存策略

| 层级 | 文件 | 字段 |
|------|------|------|
| 默认值 | `app_config.json` | `sidebar_width`, `category_list_width` |
| 用户覆盖 | `user_config.json` | `sidebar_width`, `category_list_width` |

读取逻辑：`user_config → app_config → 硬编码默认（320/220）`

```python
class ResizableSidebarConfig:
    @staticmethod
    def load(key: str, default: int) -> int
    @staticmethod
    def save(key: str, width: int)
```

复用 `config_loader.load_user/load_app/save_user/save_app`。

---

## 4. 删除侧边栏头部

移除 `sidebar.py:40-44` 蓝色 70px header 区块（含 emoji 和"施工项目记账"文字）。

保留 `Sidebar.__init__` 的 `pack_propagate(False)`、`width=320`（宽度由 DraggableSplitter 接管后变为动态）。

---

## 5. 关于界面 GitHub 超链接

`about_panel.py` 版本信息下方添加：

```python
import webbrowser

github_link = tk.Label(
    self, text="GitHub: github.com/woshiwangnima/...",
    font=FONT_SMALL, bg=APP_BG, fg=ACCENT, cursor="hand2",
)
github_link.pack(anchor="w", pady=(4, 8))
github_link.bind("<Button-1>", lambda e: webbrowser.open(REPO_URL))
```

URL 常量 `REPO_URL = "https://github.com/woshiwangnima/construction-project-accounting"` 定义在文件顶部。

---

## 6. TooltipCarousel — 提示轮播组件

### 文件

`src/gui/widgets/tooltip_carousel.py`

### 接口

```python
class TooltipCarousel(tk.Frame):
    def __init__(
        self,
        parent,
        messages: list[str],
        dwell_per_char_ms: int = 80,
        font_size: int = 13,
        fg=TEXT_SECONDARY,
        bg=APP_BG,
    )
```

字体大小从 `app_config.tooltips.font_size` 读取，传入构造时转换为 `("Microsoft YaHei UI", font_size)`。

### 配置源

`app_config.json` 新增字段：

```json
"tooltips": {
    "messages": [
        "双击行可编辑；拖表头竖条可调列宽",
        "拖动左侧手柄可排序；右键可复制/粘贴",
        "点击「保存为图片」可导出为 PNG"
    ],
    "dwell_per_char_ms": 80,
    "font_size": 13
}
```

### 行为

1. 从 `messages[0]` 开始
2. 测量文本宽度与容器宽度对比：
   - **文本 ≤ 容器** → 静态展示 `len(text) * dwell_per_char_ms` ms 后切换下一条
   - **文本 > 容器** → 启动平移动画：
     - 从起始位置向左滚动（每 tick = 1px，间隔 `dwell_per_char_ms`）
     - 到最左端（文本末尾）后，向右滚动回到起始位置
     - 完成一个来回后，切换下一条
3. 循环往复

### 替换位置

| 文件 | 行号 | 旧标签 |
|------|------|--------|
| `content.py` | 855 | billing tab hint label |
| `content.py` | 1186 | workers tab hint label |

---

## 7. 对话框确认/取消按钮弹性贴底

### 修改范围

`edit_bill.py` (EditBillDialog) 和 `edit_trade.py` (EditTradeItemDialog)

### 布局调整

```
wrap (tk.Frame, fill=BOTH, expand=True)
├── canvas (ScrollableFrame: 填充上半部分, expand=True)
│   └── content_frame (所有业务字段)
├── (scrollbar — 在ScrollableFrame内部)
├── spacer_frame (pack fill=BOTH expand=True ← 弹性撑满)
└── btn_frame (pack pady, 底部居中)
    ├── 取消按钮 (ghost)
    └── 确定按钮 (primary)
```

- `btn_frame` 从 `content_frame` 移出到 wrap 层
- spacer 确保按钮始终在可视区域底部
- 内容过长时，用户需滚动到底部看到按钮（即 B 方案：内容底部模式）

---

## 实施顺序

1. `ScrollableFrame` 组件（最基础的依赖）
2. `DraggableSplitter` 组件
3. 侧边栏宽度可调整 + 分类列表宽度可调整
4. 删除侧边栏头部
5. 替换所有旧 scrollable 实现为 ScrollableFrame
6. 设置面板（基础/语音/关于）添加滚动支持
7. 修复编辑图标
8. GitHub 超链接
9. TooltipCarousel 组件 + 替换 hint 标签
10. 对话框按钮布局调整

## 文件变更清单

| 操作 | 文件 |
|------|------|
| 新增 | `src/gui/widgets/scrollable_frame.py` |
| 新增 | `src/gui/widgets/draggable_splitter.py` |
| 新增 | `src/gui/widgets/tooltip_carousel.py` |
| 修改 | `src/gui/sidebar.py` — 替换 scrollable, 添加分隔条, 删除头部 |
| 修改 | `src/gui/content.py` — 图标替换, 分类列表改可拖动, tooltip替换 |
| 修改 | `src/gui/main_window.py` — separator 改为分隔条 |
| 修改 | `src/gui/widgets/__init__.py` — 替换 `_make_scrollable` |
| 修改 | `src/gui/dialogs/edit_bill.py` — 按钮布局调整 |
| 修改 | `src/gui/dialogs/edit_trade.py` — 按钮布局调整 |
| 修改 | `src/gui/dialogs/settings/basic_panel.py` — 添加滚动 |
| 修改 | `src/gui/dialogs/settings/voice_panel.py` — 添加滚动 |
| 修改 | `src/gui/dialogs/settings/about_panel.py` — 添加滚动 + GitHub链接 |
| 修改 | `src/gui/dialogs/settings/export_panel.py` — 替换 `_make_scrollable` |
| 修改 | `config/app_config.json` — 新增 toolbar/分类宽度默认值, tooltips配置 |
| 修改 | `config/user_config.json` — 新增可写字段 |
