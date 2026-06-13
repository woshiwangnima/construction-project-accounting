# TableHeader 组件提取 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Extract ListViewBase header rendering into standalone TableHeader component with dynamic wrapping and generic header click callbacks.

**Architecture:** New `table_header.py` with `TableHeader(tk.Frame)` class; ListViewBase delegates header building to it; BillListView passes `header_click_map` instead of overriding `_build_header`.

**Tech Stack:** Python 3, Tkinter

---

### Task 1: Create TableHeader component

**Files:**
- Create: `src/gui/widgets/table_header.py`

- [ ] **Step 1: Write the component**

```python
"""表头组件：支持动态换行动态行高 + 列头点击回调"""

import tkinter as tk

from ..theme import FONT_BODY_BOLD, TEXT_PRIMARY


class TableHeader(tk.Frame):
    HANDLE_WIDTH = 4
    HANDLE_BG = "#a0aec0"
    HANDLE_HOVER_BG = "#718096"

    def __init__(self, parent, columns, pixels, header_click_map=None,
                 on_drag_start=None):
        super().__init__(parent, bg="#e8e8e8")
        self._columns = columns
        self._pixels = pixels
        self._header_click_map = header_click_map or {}
        self._on_drag_start = on_drag_start
        self._cells: dict[str, tk.Frame] = {}
        self._labels: dict[str, tk.Label] = {}
        self._build()
        self._bind_clicks()

    def _build(self):
        for idx, col in enumerate(self._columns):
            self.grid_columnconfigure(idx, minsize=self._pixels.get(col, 80))
            cell = tk.Frame(self, bg="#e8e8e8")
            lbl = tk.Label(cell, text=col, font=FONT_BODY_BOLD, bg="#e8e8e8",
                           fg=TEXT_PRIMARY, anchor="w", padx=8, wraplength=0)
            lbl.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
            if idx < len(self._columns) - 1:
                handle = tk.Frame(cell, bg=self.HANDLE_BG,
                                  width=self.HANDLE_WIDTH, cursor="sb_h_double_arrow")
                handle.pack(side=tk.RIGHT, fill=tk.Y)
                if self._on_drag_start:
                    handle.bind("<ButtonPress-1>",
                                lambda e, i=idx: self._on_drag_start(i, e))
                    handle.bind("<Enter>", lambda e, h=handle: h.config(bg=self.HANDLE_HOVER_BG))
                    handle.bind("<Leave>", lambda e, h=handle: h.config(bg=self.HANDLE_BG))
            cell.grid(row=0, column=idx, sticky="nsew")
            self._cells[col] = cell
            self._labels[col] = lbl

    def _bind_clicks(self):
        for col, callback in self._header_click_map.items():
            lbl = self._labels.get(col)
            if lbl:
                lbl.config(cursor="hand2")
                lbl.bind("<Button-1>", lambda e, c=col: callback(c))

    def refresh_widths(self, pixels: dict[str, int]):
        self._pixels = pixels
        for idx, col in enumerate(self._columns):
            self.grid_columnconfigure(idx, minsize=pixels.get(col, 80))
            lbl = self._labels.get(col)
            if lbl:
                lbl.config(wraplength=max(pixels.get(col, 80) - 16, 8))
```

- [ ] **Step 2: Verify syntax**

```bash
python -c "import py_compile; py_compile.compile('src/gui/widgets/table_header.py', doraise=True); print('OK')"
```

---

### Task 2: Modify ListViewBase

**Files:**
- Modify: `src/gui/widgets/list_view_base.py`

- [ ] **Step 1: Read the current file to understand context**

- [ ] **Step 2: Add `header_click_map` parameter to `__init__`**

Find the `__init__` method (around line 55-95). Add parameter:

```python
def __init__(self, parent, *, columns, default_weights=None,
             min_width=40, action_col="操作", action_col_width=180,
             on_column_resize=None, on_row_activated=None,
             on_reorder=None, on_delete=None,
             header_click_map=None,    # <-- ADD THIS
             bg="white", wrap_cols=(), editable=True):
```

And in the body, add:

```python
self._header_click_map = header_click_map or {}
```

- [ ] **Step 3: Replace `_build_header` method**

Replace the entire `_build_header` method (currently ~22 lines, around line 225-246):

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

- [ ] **Step 4: Update `_refresh_widths` to delegate header refresh**

Locate the `_refresh_widths` method (around line 346). The header-specific code (looping over grid_slaves and setting minsize) should be replaced with:

```python
def _refresh_widths(self):
    if not self._header or not self._body:
        return
    self.update_idletasks()
    total_w = self._table_viewport_width()
    specs = self._column_specs()
    pixels = compute_column_pixels(specs, self._weights, total_w)
    self._pixels = pixels

    self._header.refresh_widths(pixels)

    for widgets in self._row_widgets:
        first_cell = next(iter(widgets.values()), None)
        if first_cell is None:
            continue
        row_frame = first_cell.master
        for idx, col in enumerate(self._columns):
            row_frame.grid_columnconfigure(idx, minsize=pixels[col])
        for wrap_col in self._wrap_cols:
            w = widgets.get(wrap_col)
            if w is not None:
                try:
                    w.config(wraplength=max(pixels[wrap_col] - 16, 8))
                except tk.TclError:
                    pass
```

The key change is: remove the header loop (lines 355-358 in original), replace with `self._header.refresh_widths(pixels)`.

- [ ] **Step 5: Verify syntax**

```bash
python -c "import py_compile; py_compile.compile('src/gui/widgets/list_view_base.py', doraise=True); print('OK')"
```

---

### Task 3: Modify BillListView

**Files:**
- Modify: `src/gui/widgets/bill_list_view.py`

- [ ] **Step 1: Remove `_build_header` method**

Delete the entire `_build_header` method override (around lines 88-98):

```python
# DELETE THIS WHOLE METHOD:
def _build_header(self):
    super()._build_header()
    if self._on_review_header_toggle is None or "审核" not in self._columns:
        return
    idx = self._columns.index("审核")
    for cell in self._header.grid_slaves(row=0, column=idx):
        for child in cell.winfo_children():
            if isinstance(child, tk.Label):
                if self._editable:
                    child.config(cursor="hand2")
                    child.bind("<Button-1>", lambda e: self._on_review_header_toggle())
```

- [ ] **Step 2: Pass `header_click_map` in `__init__`**

Find the `__init__` method of `BillListView`. Add `header_click_map` to the `super().__init__()` call:

```python
class BillListView(ListViewBase):
    def __init__(self, parent, *, bills=None, on_review_toggle=None,
                 on_review_header_toggle=None, editable=True,
                 on_reorder=None, on_delete=None, **kwargs):
        review_header_toggle = on_review_header_toggle
        header_click_map = {}
        if review_header_toggle is not None and "审核" in BILLS_COLUMNS:
            header_click_map["审核"] = lambda col: review_header_toggle()
        super().__init__(
            parent,
            columns=BILLS_FULL_COLUMNS,
            default_weights=default_weights or None,
            min_width=BILLS_MIN_WIDTH,
            action_col="操作",
            action_col_width=104,
            on_column_resize=save_bill_weights,
            on_row_activated=on_row_activated,
            on_reorder=on_reorder,
            on_delete=on_delete,
            bg=APP_BG,
            wrap_cols=BILLS_WRAP_COLS,
            editable=editable,
            header_click_map=header_click_map,   # <-- ADD THIS
        )
```

Note: The actual `super().__init__()` call may look different - I need to read the current file to see the exact structure. The key point is adding `header_click_map=header_click_map` to the call.

- [ ] **Step 3: Verify syntax**

```bash
python -c "import py_compile; py_compile.compile('src/gui/widgets/bill_list_view.py', doraise=True); print('OK')"
```

---

### Verification

- [ ] **Run the app and check:**
  1. Bills tab header renders correctly ("#", "审核", "工作内容", ...) with no fixed height
  2. Click "审核" header column → all bills toggle reviewed state
  3. Drag column handles still work
  4. Workers tab header renders correctly (no regression)
