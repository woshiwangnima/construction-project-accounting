# 列表列宽权重配置设计方案

## 概述

为侧边栏项目列表和分类列表的行内元素（名称/状态、名称/计数）添加基于归一化权重的比例布局，权重由开发者通过 `app_config.json` 预设，应用只读不写。

## 配置结构

`config/app_config.json` 新增字段：

```json
{
  "list_column_weights": {
    "project_list": {
      "name": 0.85,
      "status": 0.15
    },
    "category_list": {
      "name": 0.80,
      "count": 0.20
    }
  }
}
```

- 权重归一化基准 = **主窗口宽度**
- 实际像素 = `主窗口宽度 × 权重`
- 每列最小 60px
- `config_loader.load_app()` 读取，`src/config_loader.py:get_app_config()` 多一层 `.get("list_column_weights", {})` 取值

## 默认值（硬编码 fallback）

`src/gui/sidebar.py`（项目列表）：
```python
PROJECT_LIST_DEFAULT_WEIGHTS = {"name": 0.85, "status": 0.15}
```

`src/gui/content.py`（分类列表）：
```python
CATEGORY_LIST_DEFAULT_WEIGHTS = {"name": 0.80, "count": 0.20}
```

读取优先级：`app_config["list_column_weights"][key]` → 硬编码默认值。

## 项目列表改造

**文件：** `src/gui/sidebar.py`

### 当前行布局（~line 180）
```
row_frame (tk.Frame)
  ├── name_frame (pack fill=X expand)
  │   ├── name_lbl (pack side=LEFT)
  │   └── status_lbl (pack side=RIGHT)
```

### 改为
```
row_frame (tk.Frame)
  ├── name_lbl (grid row=0 col=0 sticky="nsew", wraplength=动态)
  └── status_lbl (grid row=0 col=1 sticky="nsew", wraplength=动态)
```

- `row_frame.grid_columnconfigure(0, weight=name_weight)`
- `row_frame.grid_columnconfigure(1, weight=status_weight)`
- 绑定 row_frame `<Configure>` → 获取当前列宽 → 更新 `wraplength`
- `anchor="w"`（名称左对齐）/ `anchor="e"`（状态右对齐）

### 读取函数
```python
def get_project_list_weights(app_config):
    weights = app_config.get("list_column_weights", {}).get("project_list", {})
    return {
        "name": weights.get("name", PROJECT_LIST_DEFAULT_WEIGHTS["name"]),
        "status": weights.get("status", PROJECT_LIST_DEFAULT_WEIGHTS["status"]),
    }
```

## 分类列表改造

**文件：** `src/gui/content.py`

### 当前位置（~line 1130-1160，`_refresh_category_list` 方法）
```
cat_row (tk.Frame)
  ├── name_lbl (pack side=LEFT)
  └── count_lbl (pack side=RIGHT)
```

### 改为
```
cat_row (tk.Frame)
  ├── name_lbl (grid row=0 col=0 sticky="nsew")
  └── count_lbl (grid row=0 col=1 sticky="nsew")
```

- 同上，grid + columnconfigure 权重 + `<Configure>` 更新 wraplength

### 读取函数
```python
def get_category_list_weights(app_config):
    weights = app_config.get("list_column_weights", {}).get("category_list", {})
    return {
        "name": weights.get("name", CATEGORY_LIST_DEFAULT_WEIGHTS["name"]),
        "count": weights.get("count", CATEGORY_LIST_DEFAULT_WEIGHTS["count"]),
    }
```

## 不涉及改动

| 项目 | 说明 |
|------|------|
| 滚动条 | 已通过 `ScrollableFrame(auto_hide_ms=None)` 始终可见 |
| `user_config.json` | 本功能只读不写 |
| 主窗口权重读取 | 通过 `MainInterface._main_pane` 的 `winfo_width()` 获取主窗口宽度 |
| 现有 bills/workers 权重逻辑 | 保持不变 |

## 文件变更清单

| 操作 | 文件 |
|------|------|
| 修改 | `src/gui/sidebar.py` — 项目列表行改为 grid + 权重布局 |
| 修改 | `src/gui/content.py` — 分类列表行改为 grid + 权重布局 |
| 修改 | `config/app_config.json` — 新增 `list_column_weights` |
