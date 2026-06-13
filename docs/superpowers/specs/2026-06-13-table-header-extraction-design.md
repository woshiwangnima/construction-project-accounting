# TableHeader 组件提取 + Header 点击回调设计方案

## 概述

将 `ListViewBase` 的表头渲染逻辑提取为独立 `TableHeader` 组件，使其支持动态换行动态行高，并增加通用的列头点击回调机制。

## 架构

### 新增文件

`src/gui/widgets/table_header.py`

`TableHeader(tk.Frame)` 类，职责：
- 渲染表头行：每列 = `tk.Label`（文本）+ `tk.Frame`（拖拽手柄，末列除外）
- 动态行高：不固定高度，`wraplength` 根据列宽实时更新，行高由内容自适应
- 列头点击：根据 `header_click_map` 绑定 `<Button-1>` + `cursor="hand2"`
- 拖拽事件转发：`on_drag_start` 回调交由 `ListViewBase` 处理

### 修改文件

| 文件 | 改动 |
|------|------|
| `src/gui/widgets/list_view_base.py` | `_build_header` 改为创建 `TableHeader` 实例；新增 `header_click_map` 参数；`_refresh_widths` 委托 header 刷新 |
| `src/gui/widgets/bill_list_view.py` | 移除自定义 `_build_header` override，改用 `header_click_map={"审核": ...}` |
| `src/gui/widgets/worker_list_view.py` | 无改动（无 header click） |

### 不受影响

- 数据行渲染、行高动态、`wrap_cols` 逻辑
- 拖拽 `_on_drag_start/motion/release` 逻辑（仍在 `ListViewBase`）
- `content.py` 的 `_toggle_all_bills_reviewed` 回调链路
- 列宽计算管线 `_column_specs → compute_column_pixels`

## TableHeader 接口

```python
class TableHeader(tk.Frame):
    def __init__(
        self,
        parent,
        columns: tuple[str, ...],
        pixels: dict[str, int],
        header_click_map: dict[str, Callable[[str], None]] | None = None,
        on_drag_start: Callable[[int, tk.Event], None] | None = None,
    )

    def refresh_widths(self, pixels: dict[str, int]) -> None
```

### 内部结构

```
header (TableHeader, tk.Frame)  — no fixed height, pack fill=X
├── [col 0] cell_frame (tk.Frame, grid sticky="nsew")
│   ├── lbl (tk.Label, pack left fill both expand, wraplength=动态)
│   └── drag_handle (tk.Frame, pack right fill Y, width=4)  — 末列无
├── [col 1] cell_frame ...
└── ...
```

### 换行逻辑

- `refresh_widths` 中为每个 `_labels[col]` 设 `wraplength=max(pixels[col] - 16, 8)`
- 所有列均启用换行（不设 `wrap_cols` 开关）

### 点击回调逻辑

`_bind_clicks` 遍历 `header_click_map`，对对应列的 label 绑定 `<Button-1>`，回调签名 `callback(col_name: str)`。

## ListViewBase 改动

### 新增参数

```python
class ListViewBase:
    def __init__(self, ..., header_click_map: dict[str, Callable] | None = None):
        self._header_click_map = header_click_map or {}
```

### _build_header 简化

```python
def _build_header(self):
    from .table_header import TableHeader
    self._header = TableHeader(
        self, self._columns, self._pixels or {},
        header_click_map=self._header_click_map,
        on_drag_start=self._on_drag_start,
    )
    self._header.pack(fill=tk.X)
```

### _refresh_widths 调整

```python
def _refresh_widths(self):
    ...
    pixels = compute_column_pixels(specs, self._weights, total_w)
    self._pixels = pixels
    self._header.refresh_widths(pixels)
    # 数据行部分不变
    for widgets in self._row_widgets:
        ...
```

## BillListView 改动

移除 `_build_header` 方法（原 bill_list_view.py:88-98），改为在 `__init__` 传参：

```python
class BillListView(ListViewBase):
    def __init__(self, parent, ..., on_review_header_toggle=None):
        header_click_map = {}
        if on_review_header_toggle is not None and "审核" in BILLS_COLUMNS:
            header_click_map["审核"] = lambda col: on_review_header_toggle()
        super().__init__(parent, ..., header_click_map=header_click_map)
```

## WorkerListView 改动

无。不传 `header_click_map` 即可。

## 文件变更清单

| 操作 | 文件 |
|------|------|
| 新增 | `src/gui/widgets/table_header.py` |
| 修改 | `src/gui/widgets/list_view_base.py` — `_build_header`, `_refresh_widths`, __init__ |
| 修改 | `src/gui/widgets/bill_list_view.py` — 移除 `_build_header`，改为传参 |
