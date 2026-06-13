"""列表控件基类 - 提供行选中、列宽拖拽、操作列、键盘上下键等通用逻辑。

设计目标：让「账单管理」和「工作类型」两处列表共享同一套交互模式，子类只负责
单元格渲染。

子类必须实现：
    _create_row_widgets(row_frame, idx, item) -> dict[str, widget]
        填一行：数据列单元格（dict[col_key, widget]）+ 操作列（基类已创建，
        子类可重写 _create_action_cell）。
        返回值用于 grid 配置 / 宽度应用。

子类可以重写：
    _create_action_cell(row_frame, idx) -> widget
        默认创建 RowActionButtons（3 按钮：上移/下移/删除）。

公共 API：
    set_items(items) / refresh(items)  # 数据
    set_weights(w) / get_weights()     # 列宽
    set_selected_index(i) / get_selected_index()  # 选中

约束：
- 「操作」列固定像素宽，不参与权重归一化
- 保存的列宽权重只覆盖数据列
- 列宽拖拽通过 bind_all 实现，跨子 widget 也能收到 B1-Motion
"""
import tkinter as tk
from tkinter import ttk

from ...logger import logger
from ..theme import (
    APP_BG, BORDER, TEXT_PRIMARY,
    FONT_BODY_BOLD,
)
from . import RowActionButtons
from .scroll_anchor import (
    RowGeometry,
    ScrollAnchor,
    capture_anchor_from_geometry,
    geometry_signature,
    is_geometry_stable,
    restore_y_from_anchor,
)
from .column_layout import ColumnSpec, capture_column_weights, compute_column_pixels, resize_adjacent_columns
from .canvas_scroll import scroll_canvas_units_clamped


class ListViewBase(tk.Frame):
    """自定义 Frame-based 列表基类。"""

    # 表头列宽拖拽手柄样式
    HANDLE_WIDTH = 4
    HANDLE_BG = "#a0aec0"
    HANDLE_HOVER_BG = "#4a5568"

    def __init__(
        self,
        parent,
        columns: tuple[str, ...],
        default_weights: dict,
        min_width: int = 60,
        action_col: str = "操作",
        action_col_width: int = 180,
        on_column_resize=None,
        on_move_up=None,
        on_move_down=None,
        on_delete=None,
        on_row_activated=None,
        on_copy=None,
        on_paste=None,
        on_reorder=None,
        on_top_index_change=None,
        scroll_id_getter=None,
        paste_enabled=None,
        paste_allowed=None,
        selection_bg: str = "#90cdf4",
        row_bg_getter=None,
        editable: bool = True,
        wrap_cols: tuple[str, ...] = (),
        header_click_map: dict[str, Callable[[str], None]] | None = None,
        **kwargs,
    ):
        bg = kwargs.pop("bg", APP_BG)
        super().__init__(parent, bg=bg, **kwargs)
        # ── 列定义 ──
        self._columns = tuple(columns)
        self._action_col = action_col
        if action_col is not None:
            assert self._action_col in self._columns, \
                f"action_col '{action_col}' must be in columns {self._columns}"
        self._data_cols = tuple(c for c in self._columns if c != action_col)
        self._action_col_width = action_col_width
        self._min_width = min_width
        # wrap_cols：会随列宽调整 wraplength 的数据列名
        self._wrap_cols = tuple(wrap_cols)
        self._header_click_map = header_click_map or {}
        # ── 权重（数据列；操作列固定像素宽） ──
        if default_weights:
            self._weights = {c: float(default_weights.get(c, 0)) for c in self._columns}
        else:
            eq = 1.0 / max(len(self._columns), 1)
            self._weights = {c: eq for c in self._columns}
        # 归一化（保证 sum=1）
        s = sum(self._weights.values())
        if s > 0:
            self._weights = {c: v / s for c, v in self._weights.items()}
        # ── 回调 ──
        self._on_column_resize = on_column_resize
        self._on_move_up = on_move_up
        self._on_move_down = on_move_down
        self._on_delete = on_delete
        self._on_row_activated = on_row_activated
        self._on_copy = on_copy
        self._on_paste = on_paste
        self._on_reorder = on_reorder
        self._on_top_index_change = on_top_index_change
        self._scroll_id_getter = scroll_id_getter
        self._paste_enabled = paste_enabled
        self._paste_allowed = paste_allowed
        # ── 状态 ──
        self._selection_bg = selection_bg
        self._row_bg_getter = row_bg_getter
        self._editable = editable
        self._items: list = []
        self._row_frames: list[tk.Frame] = []
        self._row_widgets: list[dict] = []
        self._selected_idx: int | None = None
        self._pixels: dict[str, int] = {}
        # ── 拖拽状态 ──
        self._drag_col_idx: int | None = None
        self._drag_start_x_root: int = 0
        self._drag_start_width: int = 0
        self._drag_start_pixels: dict[str, int] = {}
        self._refresh_after_id: str | None = None
        self._row_drag_from: int | None = None
        self._row_drag_target: int | None = None
        self._row_drag_line: tk.Frame | None = None
        self._scroll_save_after_id: str | None = None
        self._restoring_scroll: bool = False
        # ── 内部 widget 引用 ──
        self._header: tk.Frame | None = None
        self._canvas: tk.Canvas | None = None
        self._body: tk.Frame | None = None
        # ── 构建 + 绑定 ──
        self._build()
        self.bind("<Configure>", self._on_resize)
        self.after(50, self._refresh_widths)
        # 全局 ↑/↓ 切选中行：绑在 toplevel，做焦点检查避免劫持文本框
        self.winfo_toplevel().bind("<KeyPress-Up>", self._on_arrow_key, add="+")
        self.winfo_toplevel().bind("<KeyPress-Down>", self._on_arrow_key, add="+")
        # body 空白处右键（cell 的 <Button-3> 不会冒泡到 body，所以在 cell 上单独绑）
        self._body.bind("<Button-3>", self._on_body_right_click, add="+")

    # ── 子类接口 ──

    def _create_row_widgets(self, row_frame, idx, item) -> dict:
        """子类必须实现：填一行数据列单元格。返回 {col_key: widget}。

        基类会自动在最后一列加操作列。子类也可以在返回的 dict 中包含
        "操作" key 来自定义操作列。
        """
        raise NotImplementedError

    def _create_action_cell(self, row_frame, idx, col_idx) -> tk.Widget:
        """默认创建操作列：拖拽手柄 + 删除。"""
        action_frame = tk.Frame(row_frame, bg=row_frame.cget("bg"))
        action_frame.grid(row=0, column=col_idx, sticky="ns", padx=4, pady=4)
        row_frame.grid_columnconfigure(col_idx, minsize=self._action_col_width)
        if self._on_reorder:
            handle = self._make_action_button(
                action_frame,
                text="☰ 拖动",
                fg="#2d3748",
                cursor="hand2" if self._editable else "arrow",
            )
            handle.config(state=tk.NORMAL if self._editable else tk.DISABLED)
            handle.pack(side=tk.LEFT, padx=(0, 6), expand=False)
            if self._editable:
                handle.bind("<ButtonPress-1>", lambda e, i=idx: self._on_row_drag_start(i, e))
                handle.bind("<B1-Motion>", self._on_row_drag_motion)
                handle.bind("<ButtonRelease-1>", self._on_row_drag_release)
            delete_btn = self._make_action_button(
                action_frame,
                text="🗑 删除",
                fg="#c0392b",
                command=(lambda i=idx: self._on_delete and self._on_delete(i)) if self._editable else None,
            )
            delete_btn.config(state=tk.NORMAL if self._editable else tk.DISABLED)
            delete_btn.pack(side=tk.LEFT, expand=False)
            return action_frame
        btns = RowActionButtons(
            action_frame,
            labels=("", "", "删除"),
            button_width=4,
            on_delete=(lambda i=idx: self._on_delete and self._on_delete(i))
            if self._editable else None,
        )
        for key in ("up", "down"):
            btns._buttons[key].pack_forget()
        btns.set_enabled(move_up=False, move_down=False, delete=self._editable)
        btns.pack(side=tk.LEFT, expand=False)
        return btns

    def _make_action_button(self, parent, text: str, fg: str, command=None, cursor: str = "hand2") -> tk.Button:
        return tk.Button(
            parent,
            text=text,
            font=FONT_BODY_BOLD,
            command=command,
            bg="white",
            fg=fg,
            activebackground="#edf2f7",
            activeforeground=fg,
            relief="groove",
            bd=1,
            cursor=cursor,
            padx=8,
            pady=2,
        )

    # ── 构建 ──

    def _build(self):
        self._build_header()
        self._build_body()
        self._render_rows()

    def _build_header(self):
        from .table_header import TableHeader
        self._header = TableHeader(
            self, self._columns, self._pixels or {},
            header_click_map=self._header_click_map,
            on_drag_start=self._on_drag_start,
        )
        self._header.pack(fill=tk.X)

    def _build_body(self):
        outer = tk.Frame(self, bg=APP_BG)
        outer.pack(fill=tk.BOTH, expand=True)
        self._canvas = tk.Canvas(outer, borderwidth=0, highlightthickness=0, bg="white")
        scrollbar = ttk.Scrollbar(outer, orient=tk.VERTICAL, command=self._canvas.yview)
        logger.debug("ListViewBase._build_body: outer created, self width=%s", self.winfo_width())
        scrollbar.config(command=self._on_scrollbar)
        self._canvas.configure(yscrollcommand=scrollbar.set)
        self._body = tk.Frame(self._canvas, bg="white")
        win_id = self._canvas.create_window((0, 0), window=self._body, anchor="nw")
        self._body.bind(
            "<Configure>",
            lambda e: self._canvas.configure(scrollregion=self._canvas.bbox("all")),
        )
        self._canvas.bind(
            "<Configure>",
            lambda e, wid=win_id: self._canvas.itemconfig(wid, width=e.width),
        )
        self._canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        # 滚轮
        self._canvas.bind("<MouseWheel>", self._on_mousewheel)
        self._body.bind("<MouseWheel>", self._on_mousewheel)

    def _on_mousewheel(self, event):
        if not self._canvas:
            return
        if scroll_canvas_units_clamped(self._canvas, int(-1 * (event.delta / 120))):
            self._schedule_top_index_change()

    def _on_scrollbar(self, *args):
        if not self._canvas:
            return
        self._canvas.yview(*args)
        self._schedule_top_index_change()

    def _schedule_top_index_change(self):
        if self._restoring_scroll or not self._on_top_index_change:
            return
        if self._scroll_save_after_id is not None:
            try:
                self.after_cancel(self._scroll_save_after_id)
            except Exception:
                pass
        self._scroll_save_after_id = self.after(300, self._fire_top_index_change)

    def _fire_top_index_change(self):
        self._scroll_save_after_id = None
        if self._on_top_index_change:
            if self._scroll_id_getter:
                self._on_top_index_change(self.get_scroll_anchor(self._scroll_id_getter))
            else:
                self._on_top_index_change(self.get_top_scroll_anchor())

    def _bind_wheel_recursive(self, widget):
        """递归给 widget 和所有后代绑滚轮，让任意子 widget 都能滚 canvas。"""
        widget.bind("<MouseWheel>", self._on_mousewheel, add="+")
        for c in widget.winfo_children():
            self._bind_wheel_recursive(c)

    def _render_rows(self):
        if self._body is None:
            return
        try:
            if not self._body.winfo_exists():
                return
        except tk.TclError:
            return
        for w in self._body.winfo_children():
            w.destroy()
        self._row_frames.clear()
        self._row_widgets.clear()
        for i, item in enumerate(self._items):
            row_frame = tk.Frame(
                self._body, bg="white", highlightbackground=BORDER,
                highlightthickness=0, bd=0, takefocus=True,
            )
            row_frame.pack(fill=tk.X, anchor="w")
            widgets = self._create_row_widgets(row_frame, i, item)
            # 操作列：若子类未提供 "操作" key，基类自动补
            if self._action_col is not None and self._action_col not in widgets:
                action_col_idx = self._columns.index(self._action_col)
                widgets[self._action_col] = self._create_action_cell(row_frame, i, action_col_idx)
            self._row_frames.append(row_frame)
            self._row_widgets.append(widgets)
        # 交替底色 + 选中行高亮
        for i in range(len(self._row_frames)):
            self._apply_row_bg(i)
        for rf in self._row_frames[:-1]:
            sep = tk.Frame(self._body, bg=BORDER, height=1)
            sep.pack(fill=tk.X)
        # 给所有行（含行内子 widget）绑滚轮
        for rf in self._row_frames:
            self._bind_wheel_recursive(rf)
        self._refresh_widths()

    # ── 列宽 ──

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
            # 找 row_frame：取任意 cell 的 master
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

    def _table_viewport_width(self) -> int:
        if self._canvas is not None:
            canvas_width = int(self._canvas.winfo_width())
            if canvas_width > 1:
                return canvas_width
        return max(int(self.winfo_width()), 400)

    def _column_specs(self) -> list[ColumnSpec]:
        content_mins = self._measure_column_content_min_widths()
        return [
            ColumnSpec(
                key=col,
                min_width=8,
                content_min_width=content_mins.get(col, 0),
                resizable=True,
            )
            for col in self._columns
        ]

    def _measure_column_content_min_widths(self) -> dict[str, int]:
        result: dict[str, int] = {}
        if not self._row_widgets:
            return result
        if self._action_col is not None:
            action_widths = []
            for widgets in self._row_widgets:
                cell = widgets.get(self._action_col)
                if cell is not None:
                    action_widths.append(max(int(cell.winfo_reqwidth()), 1))
            if action_widths:
                result[self._action_col] = max(action_widths)
        return result

    def _on_resize(self, event=None):
        if self._refresh_after_id is not None:
            try:
                self.after_cancel(self._refresh_after_id)
            except Exception:
                pass
        self._refresh_after_id = self.after(50, self._refresh_widths)

    def set_weights(self, weights: dict) -> None:
        """外部设置列宽权重。原样存，由 _refresh_widths 内部 weights_to_pixels 归一化。"""
        self._weights = dict(weights)
        self._refresh_widths()

    def get_weights(self) -> dict:
        """返回当前权重（与 set_weights 写入的一致；可能未归一化）。"""
        return dict(self._weights)

    # ── 列宽拖拽 ──

    def _on_drag_start(self, col_idx: int, event):
        self._drag_col_idx = col_idx
        self._drag_start_x_root = event.x_root
        col = self._columns[col_idx]
        self._drag_start_width = self._pixels.get(col, 100)
        self._drag_start_pixels = dict(self._pixels)
        # 用 bind_all：拖到行/列上时事件目标是子 widget，
        # self 不在子 widget 的 bindtags 链里，self.bind 不会触发。
        self.bind_all("<B1-Motion>", self._on_drag_motion, add="+")
        self.bind_all("<ButtonRelease-1>", self._on_drag_release, add="+")

    def _on_drag_motion(self, event):
        if self._drag_col_idx is None:
            return
        if self._drag_col_idx >= len(self._columns) - 1:
            return
        left_col = self._columns[self._drag_col_idx]
        right_col = self._columns[self._drag_col_idx + 1]
        delta = event.x_root - self._drag_start_x_root
        self._pixels = resize_adjacent_columns(
            self._column_specs(), self._drag_start_pixels, left_col, right_col, delta,
        )
        self._header.refresh_widths(self._pixels)
        for widgets in self._row_widgets:
            first_cell = next(iter(widgets.values()), None)
            if first_cell is None:
                continue
            row_frame = first_cell.master
            for idx, col in enumerate(self._columns):
                row_frame.grid_columnconfigure(idx, minsize=self._pixels[col])
            for col_name in self._wrap_cols:
                w = widgets.get(col_name)
                if w is not None:
                    w.config(wraplength=max(self._pixels[col_name] - 16, 8))

    def _on_drag_release(self, event):
        # 守卫：没在拖时收到 release 也要清理 binding
        if self._drag_col_idx is None:
            self.unbind_all("<B1-Motion>")
            self.unbind_all("<ButtonRelease-1>")
            return
        col_idx = self._drag_col_idx
        col = self._columns[col_idx]
        self._drag_col_idx = None
        self.unbind_all("<B1-Motion>")
        self.unbind_all("<ButtonRelease-1>")
        # 没真拖动（按下和松开之间像素宽没变）→ 不触发回调
        if self._pixels.get(col, 0) == self._drag_start_width:
            return

        # 强制布局更新
        self.update_idletasks()

        # 读取所有列的实际宽度，包括「操作」列。
        measured: dict[str, int] = {}
        for idx, c in enumerate(self._columns):
            col_index = self._columns.index(c)
            slaves = self._header.grid_slaves(row=0, column=col_index)
            if slaves:
                measured[c] = max(slaves[0].winfo_width(), self._min_width)
            else:
                measured[c] = max(self._pixels.get(c, 100), self._min_width)

        new_weights = capture_column_weights(self._column_specs(), measured)
        if not new_weights:
            return
        if new_weights == self._weights:
            return
        self._weights = new_weights
        if self._on_column_resize:
            self._on_column_resize(new_weights)

    # ── 数据 ──

    def set_items(self, items: list) -> None:
        """设置数据列表。"""
        self._items = list(items)
        # 选中行越界则清空
        if self._selected_idx is not None and self._selected_idx >= len(self._items):
            self._selected_idx = None
        self._render_rows()

    def refresh(self, items: list) -> None:
        """兼容旧 API。"""
        self.set_items(items)

    def get_top_item_index(self) -> int | None:
        anchor = self.get_top_scroll_anchor()
        return anchor.get("index") if anchor else None

    def _content_height(self) -> int:
        if not self._canvas:
            return 0
        self.update_idletasks()
        bbox = self._canvas.bbox("all")
        if not bbox:
            return 0
        return max(int(bbox[3] - bbox[1]), 1)

    def _row_geometry(self, item_id_getter) -> list[RowGeometry]:
        self.update_idletasks()
        rows: list[RowGeometry] = []
        for idx, row_frame in enumerate(self._row_frames):
            try:
                item_id = item_id_getter(idx, self._items[idx])
            except (IndexError, TypeError):
                item_id = item_id_getter(idx)
            if item_id is None:
                continue
            rows.append(RowGeometry(
                item_id=str(item_id),
                top=int(row_frame.winfo_y()),
                height=max(int(row_frame.winfo_height()), 1),
            ))
        return rows

    def _scroll_debug_state(self, rows: list[RowGeometry] | None = None) -> dict:
        if not self._canvas:
            return {}
        bbox = self._canvas.bbox("all")
        yview = self._canvas.yview()
        return {
            "widget": type(self).__name__,
            "items": len(self._items),
            "rows": len(rows) if rows is not None else len(self._row_frames),
            "canvas_height": int(self._canvas.winfo_height()),
            "canvas_width": int(self._canvas.winfo_width()),
            "content_height": self._content_height(),
            "scrollregion": self._canvas.cget("scrollregion"),
            "bbox": bbox,
            "top_y": int(self._canvas.canvasy(0)),
            "yview": yview,
            "row_sample": [
                (row.item_id, row.top, row.height)
                for row in (rows or [])[:5]
            ],
        }

    def get_scroll_anchor(self, item_id_getter) -> dict | None:
        if not self._canvas or not self._row_frames:
            return None
        anchor = capture_anchor_from_geometry(
            self._row_geometry(item_id_getter),
            top_y=int(self._canvas.canvasy(0)),
            viewport_height=max(int(self._canvas.winfo_height()), 1),
            content_height=self._content_height(),
        )
        rows = self._row_geometry(item_id_getter)
        logger.debug("scroll capture anchor=%s state=%s", anchor.to_dict() if anchor else None,
                     self._scroll_debug_state(rows))
        return anchor.to_dict() if anchor else None

    def restore_scroll_anchor(self, anchor: dict | ScrollAnchor | None, item_id_getter) -> None:
        if anchor is None or not self._canvas or not self._row_frames:
            return

        def do_scroll(previous_signature=None, attempts_left: int = 8):
            if not self._canvas or not self._row_frames:
                return
            self._restoring_scroll = True
            try:
                self.update_idletasks()
                content_height = self._content_height()
                viewport_height = max(int(self._canvas.winfo_height()), 1)
                rows = self._row_geometry(item_id_getter)
                if not rows or content_height <= 0:
                    logger.debug("scroll restore skipped anchor=%s state=%s", anchor,
                                 self._scroll_debug_state(rows))
                    return
                current_signature = geometry_signature(rows, viewport_height, content_height)
                if attempts_left > 0 and not is_geometry_stable(previous_signature, current_signature):
                    logger.debug(
                        "scroll restore waiting stable attempts_left=%s anchor=%s state=%s",
                        attempts_left, anchor, self._scroll_debug_state(rows),
                    )
                    self.after(50, lambda: do_scroll(current_signature, attempts_left - 1))
                    return
                y = restore_y_from_anchor(anchor, rows, viewport_height, content_height)
                fraction = 0.0 if content_height <= 0 else max(0.0, min(1.0, y / content_height))
                logger.debug(
                    "scroll restore apply target_y=%s fraction=%.6f attempts_left=%s anchor=%s before=%s",
                    y, fraction, attempts_left, anchor, self._scroll_debug_state(rows),
                )
                self._canvas.yview_moveto(fraction)
                self.update_idletasks()
                top_after = int(self._canvas.canvasy(0))
                max_top = max(0, content_height - viewport_height)
                logger.debug(
                    "scroll restore after top_after=%s max_top=%s state=%s",
                    top_after, max_top, self._scroll_debug_state(rows),
                )
                if attempts_left > 0 and top_after > max_top:
                    self.after(50, lambda: do_scroll(None, attempts_left - 1))
            finally:
                self._restoring_scroll = False

        self.after(50, do_scroll)

    def get_top_scroll_anchor(self) -> dict | None:
        anchor = self.get_scroll_anchor(lambda idx, item=None: idx)
        if not anchor:
            return None
        return {
            "index": int(anchor["item_id"]),
            "offset_px": anchor.get("offset_px", 0),
            "offset_ratio": anchor.get("offset_ratio", 0.0),
            "fallback_index": anchor.get("fallback_index", 0),
            "viewport_height": anchor.get("viewport_height", 0),
            "content_height": anchor.get("content_height", 0),
        }

    def scroll_to_index(self, idx: int | None, offset_ratio: float = 0.0) -> None:
        if idx is None:
            return
        anchor = ScrollAnchor(item_id=str(idx), offset_ratio=offset_ratio, fallback_index=idx)
        self.restore_scroll_anchor(anchor, lambda row_idx, item=None: row_idx)

    # ── 行选中 ──

    def get_selected_index(self) -> int | None:
        """返回当前选中行索引（按当前 items 列表），无选中返回 None。"""
        return self._selected_idx

    def set_selected_index(self, idx: int | None) -> None:
        """外部设置选中行；越界或 None 视为清空。"""
        if idx is not None and (idx < 0 or idx >= len(self._items)):
            idx = None
        prev = self._selected_idx
        self._selected_idx = idx
        if prev is not None:
            self._apply_row_bg(prev)
        if idx is not None:
            self._apply_row_bg(idx)

    def _on_row_click(self, idx: int) -> None:
        """用户点数据单元 → 选中并高亮，并让行获焦以便后续 ↑/↓ 切选中。"""
        if self._selected_idx == idx:
            return
        prev = self._selected_idx
        self._selected_idx = idx
        if prev is not None and prev < len(self._row_frames):
            self._apply_row_bg(prev)
        self._apply_row_bg(idx)
        # 让该行获焦
        if 0 <= idx < len(self._row_frames):
            rf = self._row_frames[idx]
            try:
                rf.config(takefocus=True)
                rf.focus_set()
            except Exception:
                pass

    def _apply_row_bg(self, idx: int) -> None:
        """设置单行的背景色（含直接子 widget）。"""
        if idx < 0 or idx >= len(self._row_frames):
            return
        if idx == self._selected_idx:
            bg = self._selection_bg
        elif self._row_bg_getter is not None:
            bg = self._row_bg_getter(idx, self._items[idx])
        else:
            bg = "#f7fafc" if idx % 2 == 1 else "white"
        rf = self._row_frames[idx]
        rf.config(bg=bg)
        for w in rf.winfo_children():
            try:
                w.config(bg=bg)
            except Exception:
                pass

    # ── 右键菜单 ──

    def _on_body_right_click(self, event) -> None:
        """body 空白处右键：找最近行（按 root 坐标），弹菜单。

        注意：行 cell widget 的 <Button-3> 不会冒泡到 body（bindtags 链不含 body），
        所以每个 cell widget 在 _create_row_widgets 里单独绑了 _on_row_right_click。
        这里只处理「点 body 空白处」的情况。
        """
        idx = self._row_index_at_y_root(event.y_root)
        self._on_row_right_click(event, idx)

    def _row_index_at_y_root(self, y_root: int) -> int | None:
        """按 y_root 找最近行（不依赖事件 y 相对坐标系，最稳）。"""
        if not self._row_frames or not self._body:
            return None
        try:
            body_top = self._body.winfo_rooty()
        except Exception:
            return None
        y_local = y_root - body_top
        for i, rf in enumerate(self._row_frames):
            try:
                top = rf.winfo_y()
                bot = top + rf.winfo_height()
            except Exception:
                continue
            if top <= y_local <= bot:
                return i
        return None

    def _fire_row_right_click(self, event, idx: int) -> None:
        """每个 cell 在 _create_row_widgets 里 bind：用户右键 cell → 触发本方法。

        统一走 _on_row_right_click（子类重写）。
        """
        # 同步选中该行
        if self._selected_idx != idx:
            self._on_row_click(idx)
        self._on_row_right_click(event, idx)

    def _on_row_right_click(self, event, idx: int | None) -> None:
        """右键回调（基类不假设业务；子类可重写或由外部注入 on_copy/on_paste 拼菜单）。"""
        # 默认无菜单；子类可重写
        pass

    # ── 行拖拽排序 ──

    def _on_row_drag_start(self, idx: int, event) -> None:
        if not self._editable or not self._on_reorder:
            return
        self._row_drag_from = idx
        self._row_drag_target = idx
        self._on_row_click(idx)

    def _on_row_drag_motion(self, event) -> None:
        if self._row_drag_from is None:
            return
        target = self._insertion_index_at_y_root(event.y_root)
        self._row_drag_target = target
        self._show_insertion_line(target)

    def _on_row_drag_release(self, event) -> None:
        if self._row_drag_from is None:
            return
        from_idx = self._row_drag_from
        to_idx = self._row_drag_target
        self._hide_insertion_line()
        self._row_drag_from = None
        self._row_drag_target = None
        if to_idx is None or to_idx == from_idx or to_idx == from_idx + 1:
            return
        self._on_reorder(from_idx, to_idx)

    def _insertion_index_at_y_root(self, y_root: int) -> int:
        if not self._row_frames:
            return 0
        for i, rf in enumerate(self._row_frames):
            top = rf.winfo_rooty()
            height = max(rf.winfo_height(), 1)
            if y_root < top + height / 2:
                return i
            if y_root < top + height:
                return i + 1
        return len(self._row_frames)

    def _show_insertion_line(self, target_idx: int) -> None:
        if not self._body:
            return
        self._hide_insertion_line()
        line = tk.Frame(self._body, bg="#3182ce", height=2)
        if target_idx <= 0:
            before = self._row_frames[0] if self._row_frames else None
            if before:
                line.pack(fill=tk.X, before=before)
            else:
                line.pack(fill=tk.X)
        elif target_idx >= len(self._row_frames):
            line.pack(fill=tk.X)
        else:
            line.pack(fill=tk.X, before=self._row_frames[target_idx])
        self._row_drag_line = line

    def _hide_insertion_line(self) -> None:
        if self._row_drag_line is not None:
            try:
                self._row_drag_line.destroy()
            except Exception:
                pass
            self._row_drag_line = None

    # ── 键盘上下键切换选中行 ──

    def _on_arrow_key(self, event):
        """toplevel 上的 ↑/↓ 事件。
        - 焦点在文本输入控件（Entry/Text/Combobox/Spinbox）→ 跳过
        - 焦点在 ttk.Treeview → 跳过（Treeview 自带行为）
        - 焦点在 ListViewBase 内部 → 移动选中行
        - 其它情况 → 跳过
        """
        if not self._items:
            return None
        focused = self.focus_get()
        if focused is None:
            return None
        cls = focused.winfo_class()
        if cls in ("TEntry", "Entry", "Text", "TCombobox", "Combobox", "Spinbox", "TSpinbox"):
            return None
        if cls in ("Treeview",):
            return None
        # 焦点是否在 ListViewBase 内部
        w = focused
        while w is not None:
            if w is self:
                break
            w = w.master
        else:
            return None
        delta = -1 if event.keysym == "Up" else 1
        cur = self._selected_idx
        last = len(self._items) - 1
        if cur is None:
            new = 0 if delta > 0 else last
        else:
            new = cur + delta
            # 边界硬停止
            if new < 0 or new > last:
                return None
        if new != cur:
            self.set_selected_index(new)
            return "break"
        return None


__all__ = ["ListViewBase"]
