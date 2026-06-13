# 列表列宽权重配置 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace hardcoded pack layouts in project list and category list rows with weight-based proportional grid layout, configurable via `app_config.json`.

**Architecture:** Read normalized weights from `app_config.json > list_column_weights > {project_list,category_list}` with hardcoded fallback. Each row uses `grid` with `columnconfigure` weights for proportional sizing + `<Configure>` binding to update `wraplength` for text wrapping.

**Tech Stack:** Python 3, Tkinter, `config_loader.load_app()`

---

### Task 1: Add `list_column_weights` to app config

**Files:**
- Modify: `config/app_config.json`

- [ ] **Step 1: Add the config section**

Insert before the `sidebar_width_ratio` field at line 307:

```json
  "list_column_weights": {
    "project_list": {
      "name": 0.85,
      "status": 0.15
    },
    "category_list": {
      "name": 0.80,
      "count": 0.20
    }
  },
```

---

### Task 2: Project list — weight-based proportional row layout

**Files:**
- Modify: `src/gui/sidebar.py`

In `_add_item` (line 110-182), the current row layout is:

```
name_frame (tk.Frame, pack fill=X)
  ├── name_lbl (pack side=LEFT)
  └── status_lbl (pack side=RIGHT)
```

- [ ] **Step 1: Add constants and weight helper at module top (after imports, before class)**

```python
PROJECT_LIST_DEFAULT_WEIGHTS = {"name": 0.85, "status": 0.15}

def _project_list_weights():
    from ..config_loader import load_app
    cfg = load_app().get("list_column_weights", {}).get("project_list", {})
    return {
        "name": cfg.get("name", PROJECT_LIST_DEFAULT_WEIGHTS["name"]),
        "status": cfg.get("status", PROJECT_LIST_DEFAULT_WEIGHTS["status"]),
    }
```

- [ ] **Step 2: Replace the row layout in `_add_item`**

Lines 128-144: Replace `item.pack(...)`, indicator block, `name_frame` creation, `name_lbl.pack(side=LEFT)`, `status_lbl.pack(side=RIGHT)` with:

```python
        item = tk.Frame(self.items_frame, bg=bg, cursor="hand2", padx=14, pady=12)
        item.pack(fill=tk.X, padx=8, pady=3)

        # 左侧选中指示条
        indicator = None
        if is_selected:
            indicator = tk.Frame(item, bg=ACCENT, width=4)
            indicator.pack(side=tk.LEFT, padx=(0, 10))

        weights = _project_list_weights()
        name_w = weights["name"]
        status_w = weights["status"]
        total = name_w + status_w

        content = tk.Frame(item, bg=bg)
        content.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        content.grid_columnconfigure(0, weight=name_w)
        content.grid_columnconfigure(1, weight=status_w)

        name_lbl = tk.Label(content, text=name, font=FONT_BODY_BOLD, bg=bg, fg=name_fg,
                            anchor="w", wraplength=0)
        name_lbl.grid(row=0, column=0, sticky="nsew", padx=(0, 4))

        status_lbl = tk.Label(content, text=status_text, font=FONT_SMALL, bg=bg,
                              fg=status_color, anchor="e")
        status_lbl.grid(row=0, column=1, sticky="nsew")
```

- [ ] **Step 3: Update `all_widgets`, `_set_item_bg`, and `_item_widgets` references**

Replace `name_frame` usage with `content` in the downstream code. The key changes after the grid layout:

```python
        all_widgets = [item, content, name_lbl, status_lbl]
        if indicator is not None:
            all_widgets.append(indicator)

        def _set_item_bg(color, fg_color=None):
            item.config(bg=color)
            content.config(bg=color)
            name_lbl.config(bg=color, fg=(fg_color or SIDEBAR_FG))
            status_lbl.config(bg=color)
```

And in the `_item_widgets` registration (around line 173):

```python
        self._item_widgets[uuid] = {
            "item": item,
            "name_frame": content,   # keep key "name_frame" for compat with _set_selected
            "name_lbl": name_lbl,
            "status_lbl": status_lbl,
            "indicator": indicator,
            "_set_item_bg": _set_item_bg,
            "name": name,
            "status": status,
        }
```

- [ ] **Step 4: Add `<Configure>` binding to update wraplength on resize**

Add after the grid layout code, before the `all_widgets` line:

```python
        def _update_wraplength(evt=None):
            cw = content.winfo_width()
            if cw > 0 and total > 0:
                nw = int(cw * name_w / total)
                sw = int(cw * status_w / total)
                try:
                    name_lbl.config(wraplength=max(60, nw - 8))
                    status_lbl.config(wraplength=max(60, sw - 8))
                except tk.TclError:
                    pass

        content.bind("<Configure>", _update_wraplength)
```

---

### Task 3: Category list — weight-based proportional row layout

**Files:**
- Modify: `src/gui/content.py`

In `_add_category_item` (line 1256-1290), the current category row layout uses `pack(side=LEFT/RIGHT)`.

- [ ] **Step 1: Add constants and weight helper at module top**

Find a suitable location (e.g., near `_project_category_names` function around line 290-320, or right before the `ContentArea` class at ~line 546):

```python
CATEGORY_LIST_DEFAULT_WEIGHTS = {"name": 0.80, "count": 0.20}

def _category_list_weights():
    from ..config_loader import load_app
    cfg = load_app().get("list_column_weights", {}).get("category_list", {})
    return {
        "name": cfg.get("name", CATEGORY_LIST_DEFAULT_WEIGHTS["name"]),
        "count": cfg.get("count", CATEGORY_LIST_DEFAULT_WEIGHTS["count"]),
    }
```

- [ ] **Step 2: Replace category row layout in `_add_category_item`**

Lines 1262-1274: Replace the labels and their pack calls with:

```python
        item = tk.Frame(self._cat_items_frame, bg=bg, cursor="hand2", padx=10, pady=8)
        item.pack(fill=tk.X, padx=4, pady=1)

        if is_selected:
            indicator = tk.Frame(item, bg=ACCENT, width=4)
            indicator.pack(side=tk.LEFT, padx=(0, 8))

        # 统计该分类下的工种数
        count = sum(1 for ti in self.project_data.get("trade_items", []) if _trade_item_category_name(ti, self.project_data) == cat_name)

        weights = _category_list_weights()
        name_w = weights["name"]
        count_w = weights["count"]

        content = tk.Frame(item, bg=bg)
        content.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        content.grid_columnconfigure(0, weight=name_w)
        content.grid_columnconfigure(1, weight=count_w)

        name_lbl = tk.Label(content, text=cat_name, font=FONT_BODY_BOLD, bg=bg, fg=fg,
                            anchor="w", wraplength=0)
        name_lbl.grid(row=0, column=0, sticky="nsew", padx=(0, 4))

        count_lbl = tk.Label(content, text=f"{count}项", font=FONT_SMALL, bg=bg, fg=TEXT_SECONDARY,
                             anchor="e")
        count_lbl.grid(row=0, column=1, sticky="nsew")
```

- [ ] **Step 3: Update event bindings to include inner labels**

The original `item.winfo_children()` only returns direct children (now `indicator` and `content`), missing `name_lbl`/`count_lbl`. Replace the binding block (lines 1285-1290):

```python
        bind_widgets = [item, content, name_lbl, count_lbl]
        if indicator is not None:
            bind_widgets.append(indicator)
        for w in bind_widgets:
            w.bind("<Button-1>", on_click)
            w.bind("<Button-3>", on_right_click)
            if not is_selected:
                w.bind("<Enter>", lambda e, i=item: i.config(bg="#edf2f7"))
                w.bind("<Leave>", lambda e, i=item: i.config(bg=APP_BG))
```

- [ ] **Step 4: Add `<Configure>` binding to update wraplength on resize**

Add after the grid layout code, before the binding block:

```python
        def _update_wraplength(evt=None):
            cw = content.winfo_width()
            if cw > 0:
                nw = int(cw * name_w / (name_w + count_w))
                cw2 = int(cw * count_w / (name_w + count_w))
                try:
                    name_lbl.config(wraplength=max(60, nw - 8))
                    count_lbl.config(wraplength=max(60, cw2 - 8))
                except tk.TclError:
                    pass

        content.bind("<Configure>", _update_wraplength)
```

---

### Verification

- [ ] **Step: Run the application and verify**

```bash
python main.py
```

Check:
1. Project list rows show name (left) and status (right) with proportional widths
2. Dragging main window wider/narrower — name wraps if too long
3. Category list rows show category name (left) and count (right) with proportional widths
4. Category name wraps on narrow panels
5. Verify `app_config.json` values are being read (tweak a weight to test)
6. Scrollbars are still visible on both lists (regression check)
