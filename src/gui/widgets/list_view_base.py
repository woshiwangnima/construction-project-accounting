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
from bisect import bisect_left, bisect_right
import tkinter as tk
from tkinter import ttk
from typing import Callable
import weakref

from ...logger import logger
from ..theme import (
    APP_BG, ACCENT, HIGHLIGHT_BG, ROW_STRIPE, SYSTEM_RED,
    TABLE_HEADER_BG, TEXT_PRIMARY, TEXT_SECONDARY,
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


_WHEEL_VIEWS: weakref.WeakSet = weakref.WeakSet()
# ``bind_all`` is interpreter-wide, not toplevel-wide.  Keep one shared
# dispatcher per Tk interpreter so dialogs do not multiply every wheel tick.
_WHEEL_BINDINGS: list[tuple[object, tuple[tuple[str, str], ...]]] = []


def _ensure_wheel_dispatch(toplevel) -> None:
    tkapp = getattr(toplevel, "tk", None)
    if tkapp is None:
        return
    for owner, _bindings in _WHEEL_BINDINGS:
        if owner is tkapp:
            return
    bindings = tuple(
        (sequence, toplevel.bind_all(sequence, _dispatch_mousewheel, add="+"))
        for sequence in ("<MouseWheel>", "<Button-4>", "<Button-5>")
    )
    _WHEEL_BINDINGS.append((tkapp, bindings))


def _release_wheel_dispatch(toplevel) -> None:
    tkapp = getattr(toplevel, "tk", None)
    if tkapp is None:
        return
    for view in tuple(_WHEEL_VIEWS):
        try:
            if getattr(view, "tk", None) is tkapp:
                return
        except tk.TclError:
            continue
    for index, (owner, bindings) in enumerate(_WHEEL_BINDINGS):
        if owner is not tkapp:
            continue
        for sequence, funcid in bindings:
            try:
                # Tkinter's public unbind_all() has no funcid overload; use
                # its targeted internal helper so other ``all`` bindings stay.
                toplevel._unbind(("bind", "all", sequence), funcid)
            except (tk.TclError, AttributeError):
                pass
        _WHEEL_BINDINGS.pop(index)
        return


def _dispatch_mousewheel(event) -> None:
    """Route one wheel event to the list containing the event widget.

    Binding every cell and every action button individually becomes expensive
    after a large table is rebuilt.  A single toplevel binding keeps the same
    interaction while avoiding hundreds of Tcl bindings per refresh.
    """
    widget = getattr(event, "widget", None)
    current = widget
    while current is not None:
        try:
            if isinstance(current, ListViewBase) and current in _WHEEL_VIEWS:
                if current.winfo_exists():
                    current._on_mousewheel(event)
                return
            current = getattr(current, "master", None)
        except (tk.TclError, AttributeError):
            return


class ListViewBase(tk.Frame):
    """自定义 Frame-based 列表基类。"""

    # Large refreshes yield to Tk's event loop between batches so resize,
    # close and wheel events are not frozen behind thousands of widget creates.
    RENDER_BATCH_SIZE = 32
    RENDER_BATCH_DELAY_MS = 1
    VIRTUALIZE_THRESHOLD = 80
    VIRTUAL_ROW_HEIGHT = 48
    VIRTUAL_OVERSCAN = 4

    # 表头列宽拖拽手柄样式
    HANDLE_WIDTH = 4
    HANDLE_BG = "#d1d1d6"
    HANDLE_HOVER_BG = TEXT_SECONDARY

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
        selection_bg: str = ACCENT,
        row_bg_getter=None,
        editable: bool = True,
        wrap_cols: tuple[str, ...] = (),
        header_click_map: dict[str, Callable[[str], None]] | None = None,
        hidden_cols: list[str] | None = None,
        action_delete: bool = True,
        compact_actions: bool = False,
        shared_actions: bool = False,
        header_labels: dict[str, str] | None = None,
        initial_items: list | None = None,
        column_min_widths: dict[str, int] | None = None,
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
        self._hidden_cols = set(hidden_cols or [])
        self._column_min_widths = {
            key: max(0, int(value))
            for key, value in (column_min_widths or {}).items()
            if value is not None
        }
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
        self._action_delete = action_delete
        self._compact_actions = bool(compact_actions)
        self._shared_actions = bool(shared_actions)
        self._header_labels = dict(header_labels or {})
        # ── 状态 ──
        self._selection_bg = selection_bg
        self._row_bg_getter = row_bg_getter
        self._editable = editable
        self._items: list = list(initial_items or [])
        self._row_frames: list[tk.Frame] = []
        self._row_widgets: list[dict] = []
        self._row_indices: list[int] = []
        self._selected_idx: int | None = None
        self._pixels: dict[str, int] = {}
        # ── 拖拽状态 ──
        self._drag_col_idx: int | None = None
        self._drag_start_x_root: int = 0
        self._drag_start_width: int = 0
        self._drag_start_pixels: dict[str, int] = {}
        self._refresh_after_id: str | None = None
        self._drag_row_refresh_after_id: str | None = None
        self._body_window_sync_after_id: str | None = None
        self._row_render_after_id: str | None = None
        self._row_render_generation = 0
        self._rendering = False
        self._virtualized = False
        self._virtual_window_range: tuple[int, int] = (0, 0)
        self._virtual_window_after_id: str | None = None
        self._virtual_top_spacer: tk.Frame | None = None
        self._virtual_row_host: tk.Frame | None = None
        self._virtual_bottom_spacer: tk.Frame | None = None
        self._virtual_height_cache: dict[int, int] = {}
        self._virtual_prefix_cache: list[int] | None = None
        self._width_refresh_pending = False
        self._retired_body_cleanup_after_id: str | None = None
        self._retired_bodies: list[tk.Frame] = []
        self._restore_scroll_after_id: str | None = None
        self._scroll_restore_generation = 0
        self._row_widths_dirty = True
        self._content_min_widths_cache: dict[str, int] | None = None
        self._drag_bind_ids: dict[str, str] = {}
        self._key_bind_ids: list[tuple[str, str]] = []
        self._event_toplevel = None
        self._row_drag_from: int | None = None
        self._row_drag_target: int | None = None
        self._row_drag_line: tk.Frame | None = None
        self._scroll_save_after_id: str | None = None
        self._restoring_scroll: bool = False
        # ── 内部 widget 引用 ──
        self._header: tk.Frame | None = None
        self._header_canvas: tk.Canvas | None = None
        self._header_window_id: int | None = None
        self._header_window_width: int | None = None
        self._header_scrollregion = None
        self._action_toolbar: tk.Frame | None = None
        self._action_button: tk.Menubutton | None = None
        self._action_menu: tk.Menu | None = None
        self._action_menu_indices: dict[str, int] = {}
        self._selection_status_var: tk.StringVar | None = None
        self._canvas: tk.Canvas | None = None
        self._body: tk.Frame | None = None
        self._body_window_id: int | None = None
        self._hscrollbar: ttk.Scrollbar | None = None
        self._body_window_width = 0
        self._canvas_scrollregion = None
        self._destroyed = False
        # ── 构建 + 绑定 ──
        self._build()
        _WHEEL_VIEWS.add(self)
        toplevel = self.winfo_toplevel()
        self._event_toplevel = toplevel
        _ensure_wheel_dispatch(toplevel)
        self.bind("<Configure>", self._on_resize)
        self._refresh_after_id = self.after(50, self._run_scheduled_refresh)
        # 全局 ↑/↓ 切选中行：绑在 toplevel，做焦点检查避免劫持文本框
        for sequence in ("<KeyPress-Up>", "<KeyPress-Down>"):
            funcid = toplevel.bind(sequence, self._on_arrow_key, add="+")
            if funcid:
                self._key_bind_ids.append((sequence, funcid))
        # body 空白处右键（cell 的 <Button-3> 不会冒泡到 body，所以在 cell 上单独绑）
        self._body.bind("<Button-3>", self._on_body_right_click, add="+")

    # ── 子类接口 ──

    def _create_row_widgets(self, row_frame, idx, item) -> dict:
        """子类必须实现：填一行数据列单元格。返回 {col_key: widget}。

        基类会自动在最后一列加操作列。子类也可以在返回的 dict 中包含
        "操作" key 来自定义操作列。
        """
        raise NotImplementedError

    def _update_row_widgets(self, widgets: dict, idx: int, item) -> None:
        """子类可选实现：增量刷新单行内容。

        数据行数不变时，refresh_items 会复用现有行控件、仅调用本方法更新
        显示值，避免整表销毁重建造成的界面闪烁。未实现本方法的子类会自动
        退化到全量 _render_rows，因此默认实现只需保证不抛错。
        """
        return None

    def _build_action_toolbar(self) -> None:
        """Build one contextual action menu for the whole list.

        Bill and worker rows used to each own a Menubutton and a Menu.  That
        made a refresh create hundreds of Tcl objects for controls that all
        performed the same actions.  The shared menu keeps the common path in
        one stable place and uses the current row selection as its target.
        """
        if not self._shared_actions:
            return
        from ..font_manager import font_manager

        toolbar = tk.Frame(self, bg=APP_BG, height=34)
        toolbar.pack(fill=tk.X, pady=(0, 6))
        self._action_toolbar = toolbar

        self._selection_status_var = tk.StringVar(value="未选择")
        tk.Label(
            toolbar,
            textvariable=self._selection_status_var,
            font=font_manager.get("small"),
            bg=APP_BG,
            fg=TEXT_PRIMARY,
            anchor="w",
        ).pack(side=tk.LEFT, padx=(2, 8))
        tk.Label(
            toolbar,
            text="拖动行尾手柄可排序" if self._editable else "当前项目为只读",
            font=font_manager.get("small"),
            bg=APP_BG,
            fg=TEXT_SECONDARY,
            anchor="w",
        ).pack(side=tk.LEFT)

        menu = tk.Menu(toolbar, tearoff=0)
        self._action_menu = menu
        for action, label in (
            ("edit", "编辑"),
            ("copy", "复制"),
            ("paste", "粘贴"),
            ("move_up", "上移"),
            ("move_down", "下移"),
            ("delete", "删除"),
        ):
            if action == "copy":
                menu.add_separator()
            if action == "move_up":
                menu.add_separator()
            if action == "delete":
                menu.add_separator()
            menu.add_command(
                label=label,
                command=lambda name=action: self._invoke_selected_action(name),
            )
            self._action_menu_indices[action] = menu.index(tk.END)

        button = tk.Menubutton(
            toolbar,
            text="操作 ▾",
            font=font_manager.get("small"),
            bg="white",
            fg=TEXT_PRIMARY,
            activebackground=HIGHLIGHT_BG,
            activeforeground=TEXT_PRIMARY,
            relief="flat",
            bd=0,
            cursor="hand2",
            padx=8,
            pady=2,
            menu=menu,
        )
        button.pack(side=tk.RIGHT, padx=(8, 2))
        self._action_button = button
        menu.configure(postcommand=self._refresh_action_menu_state)
        self._refresh_action_menu_state()

    @staticmethod
    def _resolve_bool(value, default: bool = False) -> bool:
        if value is None:
            return default
        try:
            return bool(value() if callable(value) else value)
        except Exception:
            return False

    def _action_capabilities(self) -> dict[str, bool]:
        idx = self._selected_idx
        has_selection = idx is not None and 0 <= idx < len(self._items)
        editable = bool(self._editable)
        can_paste = (
            editable
            and self._on_paste is not None
            and self._resolve_bool(self._paste_enabled, default=True)
            and self._resolve_bool(self._paste_allowed, default=True)
        )
        return {
            "edit": has_selection and editable and self._on_row_activated is not None,
            "copy": has_selection and self._on_copy is not None,
            "paste": can_paste,
            "move_up": has_selection and editable and idx > 0 and self._on_move_up is not None,
            "move_down": (
                has_selection and editable and idx < len(self._items) - 1
                and self._on_move_down is not None
            ),
            "delete": (
                has_selection and editable and self._action_delete
                and self._on_delete is not None
            ),
        }

    def _refresh_action_menu_state(self) -> None:
        if not self._shared_actions or self._action_menu is None:
            return
        capabilities = self._action_capabilities()
        for action, menu_index in self._action_menu_indices.items():
            try:
                self._action_menu.entryconfig(
                    menu_index,
                    state=tk.NORMAL if capabilities.get(action, False) else tk.DISABLED,
                )
            except tk.TclError:
                pass
        if self._action_button is not None:
            try:
                # The trigger must stay usable even when every menu entry is
                # currently disabled (no selection, empty list, or read-only
                # project).  Disabling the Menubutton itself hides the reason
                # an action is unavailable and makes the whole toolbar look
                # broken.  Keep the entry states contextual instead.
                self._action_button.config(state=tk.NORMAL, cursor="hand2")
            except tk.TclError:
                pass

    def _update_action_toolbar(self) -> None:
        if not self._shared_actions:
            return
        if self._selected_idx is not None and 0 <= self._selected_idx < len(self._items):
            if self._selection_status_var is not None:
                self._selection_status_var.set(f"已选择第 {self._selected_idx + 1} 行")
        else:
            self._selected_idx = None
            if self._selection_status_var is not None:
                self._selection_status_var.set("未选择")
        self._refresh_action_menu_state()

    def _invoke_selected_action(self, action: str) -> None:
        capabilities = self._action_capabilities()
        if not capabilities.get(action, False):
            return
        idx = self._selected_idx
        if action == "edit" and self._on_row_activated is not None:
            self._on_row_activated(idx)
        elif action == "copy" and self._on_copy is not None:
            self._on_copy(idx)
        elif action == "paste" and self._on_paste is not None:
            self._on_paste(idx)
        elif action == "move_up" and self._on_move_up is not None:
            self._on_move_up(idx)
        elif action == "move_down" and self._on_move_down is not None:
            self._on_move_down(idx)
        elif action == "delete" and self._on_delete is not None:
            self._on_delete(idx)

    def _bind_row_widgets(self, row_frame, idx: int, cells: dict) -> None:
        """Delegate common row events through one binding per row.

        Each cell keeps its native class behavior (for example a review
        button still receives its command), while selection/context/edit
        handling is installed once on the row frame.
        """
        row_frame.bind("<Button-1>", lambda _event, i=idx: self._on_row_click(i), add="+")
        row_frame.bind(
            "<Button-3>",
            lambda event, i=idx: self._fire_row_right_click(event, i),
            add="+",
        )
        if self._editable and self._on_row_activated is not None:
            row_frame.bind(
                "<Double-1>",
                lambda _event, i=idx: self._on_row_activated(i),
                add="+",
            )
        row_tag = row_frame._w
        for widget in cells.values():
            try:
                tags = tuple(widget.bindtags())
                if row_tag not in tags:
                    widget.bindtags((row_tag, *tags))
            except (AttributeError, tk.TclError):
                pass

    @staticmethod
    def _action_font():
        from ..font_manager import font_manager
        return font_manager.get("small")

    def _create_action_cell(self, row_frame, idx, col_idx) -> tk.Widget:
        """默认创建操作列：拖拽手柄 + 可选删除按钮。"""
        action_frame = tk.Frame(row_frame, bg=row_frame.cget("bg"))
        action_frame.grid(row=0, column=col_idx, sticky="ns", padx=6, pady=6)
        row_frame.grid_columnconfigure(col_idx, minsize=self._action_col_width)
        ft = self._action_font()
        if self._shared_actions:
            return self._create_drag_handle(action_frame, idx, ft)
        if self._compact_actions:
            return self._create_compact_action_cell(action_frame, idx, ft)
        if self._on_reorder:
            handle = self._make_action_button(
                action_frame, text="☰ 拖动", fg=TEXT_PRIMARY, font=ft,
                cursor="hand2" if self._editable else "arrow",
            )
            handle.config(state=tk.NORMAL if self._editable else tk.DISABLED)
            handle.pack(side=tk.LEFT, padx=(0, 6), expand=False)
            if self._editable:
                handle.bind("<ButtonPress-1>", lambda e, i=idx: self._on_row_drag_start(i, e))
                handle.bind("<B1-Motion>", self._on_row_drag_motion)
                handle.bind("<ButtonRelease-1>", self._on_row_drag_release)
            if self._action_delete:
                delete_btn = self._make_action_button(
                    action_frame, text="🗑 删除", fg=SYSTEM_RED, font=ft,
                    command=(lambda i=idx: self._on_delete and self._on_delete(i)) if self._editable else None,
                )
                delete_btn.config(state=tk.NORMAL if self._editable else tk.DISABLED)
                delete_btn.pack(side=tk.LEFT, expand=False)
            return action_frame
        if self._action_delete:
            btns = RowActionButtons(
                action_frame, labels=("", "", "删除"), button_width=4, font=ft,
                on_delete=(lambda i=idx: self._on_delete and self._on_delete(i))
                if self._editable else None,
            )
            for key in ("up", "down"):
                btns._buttons[key].pack_forget()
            btns.set_enabled(move_up=False, move_down=False, delete=self._editable)
            btns.pack(side=tk.LEFT, expand=False)
            return btns
        return action_frame

    def _create_drag_handle(self, action_frame, idx, font) -> tk.Widget:
        """Create the only per-row control: a small reorder handle."""
        if not self._on_reorder:
            return action_frame
        handle = tk.Label(
            action_frame,
            text="⋮⋮",
            font=font,
            bg="white",
            fg=TEXT_SECONDARY,
            cursor="fleur" if self._editable else "arrow",
            padx=4,
            pady=1,
        )
        handle.pack(side=tk.LEFT, padx=2, expand=False)
        if self._editable:
            handle.bind("<ButtonPress-1>", lambda e, i=idx: self._on_row_drag_start(i, e))
            handle.bind("<B1-Motion>", self._on_row_drag_motion)
            handle.bind("<ButtonRelease-1>", self._on_row_drag_release)
        return action_frame

    def _create_compact_action_cell(self, action_frame, idx, font) -> tk.Widget:
        """Use one menu entry while keeping the drag grip for reordering."""
        if self._on_reorder:
            grip = tk.Label(
                action_frame, text="↕", font=font, bg="white", fg=TEXT_SECONDARY,
                cursor="fleur" if self._editable else "arrow", padx=2,
            )
            grip.pack(side=tk.LEFT, padx=(0, 2))
            if self._editable:
                grip.bind("<ButtonPress-1>", lambda e, i=idx: self._on_row_drag_start(i, e))
                grip.bind("<B1-Motion>", self._on_row_drag_motion)
                grip.bind("<ButtonRelease-1>", self._on_row_drag_release)

        menu = tk.Menu(action_frame, tearoff=0)
        has_action = False
        if self._on_move_up:
            menu.add_command(label="上移", command=lambda i=idx: self._on_move_up(i))
            has_action = True
        if self._on_move_down:
            menu.add_command(label="下移", command=lambda i=idx: self._on_move_down(i))
            has_action = True
        if self._action_delete and self._on_delete:
            if has_action:
                menu.add_separator()
            menu.add_command(label="删除", command=lambda i=idx: self._on_delete(i))
            has_action = True

        button = tk.Menubutton(
            action_frame, text="操作 ▾", font=font, bg="white", fg=TEXT_PRIMARY,
            activebackground=HIGHLIGHT_BG, activeforeground=TEXT_PRIMARY,
            relief="flat", bd=0, cursor="hand2" if has_action else "arrow",
            padx=4, pady=1, menu=menu,
        )
        button.config(state=tk.NORMAL if self._editable and has_action else tk.DISABLED)
        button.pack(side=tk.LEFT, expand=False)
        menu.configure(postcommand=lambda m=menu, i=idx: self._update_action_menu_state(m, i))
        return action_frame

    def _update_action_menu_state(self, menu, idx: int) -> None:
        if idx < 0 or idx >= len(self._items):
            return
        try:
            if self._on_move_up:
                menu.entryconfig("上移", state=tk.NORMAL if self._editable and idx > 0 else tk.DISABLED)
            if self._on_move_down:
                menu.entryconfig(
                    "下移",
                    state=tk.NORMAL if self._editable and idx < len(self._items) - 1 else tk.DISABLED,
                )
            if self._action_delete and self._on_delete:
                menu.entryconfig("删除", state=tk.NORMAL if self._editable else tk.DISABLED)
        except tk.TclError:
            pass

    def _add_reorder_menu_items(self, menu, idx: int) -> bool:
        if idx is None or idx < 0 or idx >= len(self._items):
            return False
        added = False
        if self._on_move_up:
            menu.add_command(
                label="上移",
                state=tk.NORMAL if self._editable and idx > 0 else tk.DISABLED,
                command=lambda i=idx: self._on_move_up(i),
            )
            added = True
        if self._on_move_down:
            menu.add_command(
                label="下移",
                state=tk.NORMAL if self._editable and idx < len(self._items) - 1 else tk.DISABLED,
                command=lambda i=idx: self._on_move_down(i),
            )
            added = True
        return added

    def _make_action_button(self, parent, text: str, fg: str, font, command=None, cursor: str = "hand2") -> tk.Button:
        return tk.Button(
            parent,
            text=text,
            font=font,
            command=command,
            bg="white",
            fg=fg,
            activebackground=HIGHLIGHT_BG,
            activeforeground=fg,
            relief="flat",
            bd=0,
            cursor=cursor,
            padx=4,
            pady=1,
        )

    # ── 构建 ──

    def _build(self):
        self._build_action_toolbar()
        self._build_header()
        self._build_body()
        self._render_rows()

    def _build_header(self):
        from .table_header import TableHeader
        self._header_canvas = tk.Canvas(
            self,
            height=1,
            borderwidth=0,
            highlightthickness=0,
            bg=TABLE_HEADER_BG,
        )
        self._header_canvas.pack(fill=tk.X)
        self._header = TableHeader(
            self, self._columns, self._pixels or {},
            header_click_map=self._header_click_map,
            on_drag_start=self._on_drag_start,
            display_names=self._header_labels,
        )
        self._header_window_id = self._header_canvas.create_window(
            (0, 0), window=self._header, anchor="nw"
        )
        self._header.bind("<Configure>", self._on_header_configure)
        self._header_canvas.bind("<Configure>", self._on_header_canvas_configure)

    def _on_header_configure(self, _event=None) -> None:
        if not self._header_canvas or not self._header:
            return
        try:
            header_height = max(int(self._header.winfo_reqheight()), 1)
            self._header_canvas.configure(height=header_height)
            content_width = self._body_window_width or int(self._header.winfo_reqwidth())
            self._sync_header_window_width(content_width)
        except tk.TclError:
            pass

    def _on_header_canvas_configure(self, event=None) -> None:
        if not self._header_canvas:
            return
        width = int(event.width) if event is not None else int(self._header_canvas.winfo_width())
        self._sync_header_window_width(max(self._body_window_width, width))

    def _sync_header_window_width(self, content_width: int) -> None:
        if not self._header_canvas or self._header_window_id is None:
            return
        try:
            viewport_width = max(int(self._header_canvas.winfo_width()), 1)
            width = max(int(content_width), viewport_width)
            height = max(int(self._header_canvas.winfo_height()), 1)
            if width != self._header_window_width:
                self._header_canvas.itemconfigure(self._header_window_id, width=width)
                self._header_window_width = width
            scrollregion = (0, 0, width, height)
            if scrollregion != self._header_scrollregion:
                self._header_canvas.configure(scrollregion=scrollregion)
                self._header_scrollregion = scrollregion
        except tk.TclError:
            pass

    def _build_body(self):
        outer = tk.Frame(self, bg=APP_BG)
        outer.pack(fill=tk.BOTH, expand=True)
        self._canvas = tk.Canvas(outer, borderwidth=0, highlightthickness=0, bg="white")
        scrollbar = ttk.Scrollbar(outer, orient=tk.VERTICAL, command=self._on_scrollbar)
        self._hscrollbar = ttk.Scrollbar(outer, orient=tk.HORIZONTAL, command=self._on_hscrollbar)
        logger.debug("ListViewBase._build_body: outer created, self width=%s", self.winfo_width())
        # Keep the header viewport the same width as the canvas viewport.  The
        # vertical scrollbar occupies this right-side space in the body.
        if self._header_canvas is not None:
            self._header_canvas.pack_configure(
                padx=(0, max(int(scrollbar.winfo_reqwidth()), 1))
            )
        self._canvas.configure(
            yscrollcommand=scrollbar.set,
            xscrollcommand=self._on_body_xscroll,
        )
        self._body = tk.Frame(self._canvas, bg="white")
        win_id = self._canvas.create_window((0, 0), window=self._body, anchor="nw")
        self._body_window_id = win_id
        self._body.bind("<Configure>", self._on_body_configure)
        self._canvas.bind("<Configure>", self._on_canvas_configure)
        outer.grid_rowconfigure(0, weight=1)
        outer.grid_columnconfigure(0, weight=1)
        self._canvas.grid(row=0, column=0, sticky="nsew")
        scrollbar.grid(row=0, column=1, sticky="ns")
        self._hscrollbar.grid(row=1, column=0, sticky="ew")
        self._hscrollbar.grid_remove()

    def _on_body_configure(self, _event=None) -> None:
        if not self._canvas or self._destroyed:
            return
        if _event is not None:
            event_widget = getattr(_event, "widget", self._body)
            if event_widget is not self._body and event_widget is not self._virtual_row_host:
                return
        self._schedule_body_window_sync()

    def _on_canvas_configure(self, _event=None) -> None:
        self._schedule_body_window_sync()

    def _schedule_body_window_sync(self) -> None:
        if self._destroyed or self._body_window_sync_after_id is not None:
            return
        self._body_window_sync_after_id = self.after_idle(
            self._sync_body_window_width
        )

    def _sync_body_window_width(self) -> None:
        self._body_window_sync_after_id = None
        if self._destroyed or not self._canvas or not self._body or self._body_window_id is None:
            return
        try:
            if not self._canvas.winfo_exists() or not self._body.winfo_exists():
                return
            viewport_width = max(int(self._canvas.winfo_width()), 1)
            requested_width = max(int(self._body.winfo_reqwidth()), 1)
            body_width = max(viewport_width, requested_width)
            if body_width != self._body_window_width:
                self._canvas.itemconfigure(self._body_window_id, width=body_width)
                self._body_window_width = body_width
            scrollregion = self._canvas.bbox("all")
            if scrollregion != self._canvas_scrollregion:
                self._canvas.configure(scrollregion=scrollregion)
                self._canvas_scrollregion = scrollregion
            self._sync_header_window_width(body_width)
            needs_horizontal = body_width > viewport_width + 1
            if self._hscrollbar is not None:
                if needs_horizontal:
                    self._hscrollbar.grid()
                else:
                    self._hscrollbar.grid_remove()
                    self._canvas.xview_moveto(0.0)
        except tk.TclError:
            return

    def _on_hscrollbar(self, *args):
        if self._canvas:
            self._canvas.xview(*args)

    def _on_body_xscroll(self, first, last):
        if self._hscrollbar is not None:
            self._hscrollbar.set(first, last)
        if self._header_canvas is not None:
            try:
                self._header_canvas.xview_moveto(float(first))
            except (ValueError, tk.TclError):
                pass

    def _on_mousewheel(self, event):
        if self._destroyed or not self._canvas:
            return
        if getattr(event, "num", None) == 4:
            units = -1
        elif getattr(event, "num", None) == 5:
            units = 1
        else:
            units = int(-1 * (getattr(event, "delta", 0) / 120))
            if units == 0 and getattr(event, "delta", 0):
                units = -1 if event.delta > 0 else 1
        if scroll_canvas_units_clamped(self._canvas, units):
            self._schedule_virtual_window_sync()
            self._schedule_top_index_change()

    def _on_scrollbar(self, *args):
        if not self._canvas:
            return
        self._canvas.yview(*args)
        self._schedule_virtual_window_sync()
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

    def _cancel_after_id(self, attr_name: str) -> None:
        timer_id = getattr(self, attr_name, None)
        if timer_id is None:
            return
        try:
            self.after_cancel(timer_id)
        except (tk.TclError, RuntimeError):
            pass
        setattr(self, attr_name, None)

    def _run_scheduled_refresh(self) -> None:
        self._refresh_after_id = None
        if self._destroyed:
            return
        if self._rendering or self._row_render_after_id is not None:
            self._width_refresh_pending = True
            return
        self._refresh_widths()

    def _bind_wheel_recursive(self, widget):
        """递归给 widget 和所有后代绑滚轮，让任意子 widget 都能滚 canvas。"""
        widget.bind("<MouseWheel>", self._on_mousewheel, add="+")
        for c in widget.winfo_children():
            self._bind_wheel_recursive(c)

    def _prepare_virtual_body(self, body: tk.Frame) -> None:
        """Create the spacer/host structure used by the virtual window."""
        self._virtual_top_spacer = tk.Frame(body, bg="white", height=1)
        self._virtual_top_spacer.pack(fill=tk.X)
        self._virtual_top_spacer.pack_propagate(False)
        self._virtual_row_host = tk.Frame(body, bg="white")
        self._virtual_row_host.pack(fill=tk.X, anchor="n")
        self._virtual_row_host.bind("<Configure>", self._on_body_configure, add="+")
        self._virtual_bottom_spacer = tk.Frame(body, bg="white", height=1)
        self._virtual_bottom_spacer.pack(fill=tk.X)
        self._virtual_bottom_spacer.pack_propagate(False)

    def _virtual_visible_range(self, total: int) -> tuple[int, int]:
        if total <= 0:
            return (0, 0)
        prefix = self._virtual_height_prefix(total)
        try:
            top_y = max(int(self._canvas.canvasy(0)), 0) if self._canvas else 0
            viewport = max(int(self._canvas.winfo_height()), self.VIRTUAL_ROW_HEIGHT)
        except tk.TclError:
            top_y, viewport = 0, self.VIRTUAL_ROW_HEIGHT * 12

        # Rows may wrap to multiple lines.  Use measured row heights when
        # known and a conservative estimate for rows that have not entered
        # the window yet, instead of assuming every row is 48 px tall.
        start_core = max(0, bisect_right(prefix, top_y) - 1)
        end_core = min(total, max(
            start_core + 1,
            bisect_left(prefix, top_y + viewport) + 1,
        ))
        start = max(0, start_core - self.VIRTUAL_OVERSCAN)
        end = min(total, end_core + self.VIRTUAL_OVERSCAN)
        window_size = max(end - start, 12)
        end = min(total, max(end, start + window_size))
        if self._selected_idx is not None and not start <= self._selected_idx < end:
            if self._selected_idx >= end:
                end = min(total, self._selected_idx + self.VIRTUAL_OVERSCAN + 1)
                start = max(0, end - window_size)
            else:
                start = max(0, self._selected_idx - self.VIRTUAL_OVERSCAN)
                end = min(total, start + window_size)
        return start, end

    def _virtual_height_prefix(self, total: int | None = None) -> list[int]:
        """Return cumulative heights for the virtual list.

        The cache contains real heights for materialized rows and falls back
        to ``VIRTUAL_ROW_HEIGHT`` for rows that have not been rendered yet.
        Keeping this model in one place makes scrolling, spacers and anchor
        restoration agree even when labels wrap to different heights.
        """
        total = len(self._items) if total is None else max(int(total), 0)
        if self._virtual_prefix_cache is not None and len(self._virtual_prefix_cache) == total + 1:
            return self._virtual_prefix_cache
        prefix = [0]
        for idx in range(total):
            height = self._virtual_height_cache.get(idx, self.VIRTUAL_ROW_HEIGHT)
            prefix.append(prefix[-1] + max(int(height), 1))
        self._virtual_prefix_cache = prefix
        return prefix

    def _virtual_anchor_at_y(self, y: int) -> tuple[int, int] | None:
        if not self._items:
            return None
        prefix = self._virtual_height_prefix()
        y = max(int(y), 0)
        idx = min(max(bisect_right(prefix, y) - 1, 0), len(self._items) - 1)
        return idx, max(y - prefix[idx], 0)

    def _virtual_scroll_to_anchor(self, idx: int, offset_px: int = 0) -> None:
        if not self._canvas or not self._items:
            return
        prefix = self._virtual_height_prefix()
        idx = min(max(int(idx), 0), len(self._items) - 1)
        viewport = max(int(self._canvas.winfo_height()), self.VIRTUAL_ROW_HEIGHT)
        total_height = max(prefix[-1], 1)
        max_top = max(total_height - viewport, 1)
        target = min(max(prefix[idx] + max(int(offset_px), 0), 0), max_top)
        # Tk's yview_moveto argument is relative to the full scrollregion,
        # not to the scrollable remainder after subtracting the viewport.
        self._canvas.yview_moveto(target / total_height)

    def _update_virtual_spacers(self, start: int, end: int, total: int) -> None:
        prefix = self._virtual_height_prefix(total)
        top_height = max(prefix[start], 0)
        bottom_height = max(prefix[-1] - prefix[end], 0)
        for spacer, height in (
            (self._virtual_top_spacer, top_height),
            (self._virtual_bottom_spacer, bottom_height),
        ):
            if spacer is None:
                continue
            try:
                spacer.configure(height=max(height, 1))
            except tk.TclError:
                pass

    def _schedule_virtual_window_sync(self) -> None:
        if not self._virtualized or self._destroyed:
            return
        if self._virtual_window_after_id is None:
            self._virtual_window_after_id = self.after_idle(
                self._sync_virtual_window
            )

    def _sync_virtual_window(self) -> None:
        self._virtual_window_after_id = None
        if not self._virtualized or self._destroyed:
            return
        self._render_virtual_window(tuple(self._items), self._row_render_generation)

    def _render_virtual_window(self, render_items: tuple, generation: int) -> None:
        if (
            self._destroyed
            or not self._virtualized
            or generation != self._row_render_generation
            or self._virtual_row_host is None
        ):
            return
        start, end = self._virtual_visible_range(len(render_items))
        if (start, end) == self._virtual_window_range and self._row_frames:
            return
        try:
            for child in self._virtual_row_host.winfo_children():
                child.destroy()
        except tk.TclError:
            return
        self._row_frames.clear()
        self._row_widgets.clear()
        self._row_indices.clear()
        self._update_virtual_spacers(start, end, len(render_items))
        for idx in range(start, end):
            item = render_items[idx]
            row_frame = tk.Frame(
                self._virtual_row_host,
                bg="white",
                highlightthickness=0,
                bd=0,
                takefocus=True,
            )
            row_frame.pack(fill=tk.X, anchor="w")
            widgets = self._create_row_widgets(row_frame, idx, item)
            if self._action_col is not None and self._action_col not in widgets:
                action_col_idx = self._columns.index(self._action_col)
                widgets[self._action_col] = self._create_action_cell(
                    row_frame, idx, action_col_idx
                )
            self._row_frames.append(row_frame)
            self._row_widgets.append(widgets)
            self._row_indices.append(idx)
            self._apply_row_bg(idx)
        self._virtual_window_range = (start, end)
        self._rendering = False
        self._refresh_widths()
        self._measure_virtual_row_heights()
        self._schedule_body_window_sync()

    def _measure_virtual_row_heights(self) -> None:
        """Record materialized row heights and refresh virtual spacers."""
        if not self._virtualized or not self._row_frames:
            return
        try:
            self.update_idletasks()
        except tk.TclError:
            return
        anchor = None
        if self._canvas is not None:
            try:
                anchor = self._virtual_anchor_at_y(int(self._canvas.canvasy(0)))
            except tk.TclError:
                anchor = None
        changed = False
        for position, row_frame in enumerate(self._row_frames):
            if position >= len(self._row_indices):
                break
            idx = self._row_indices[position]
            try:
                height = max(int(row_frame.winfo_height()), int(row_frame.winfo_reqheight()), 1)
            except tk.TclError:
                continue
            if self._virtual_height_cache.get(idx) != height:
                self._virtual_height_cache[idx] = height
                changed = True
        if not changed:
            return
        self._virtual_prefix_cache = None
        start, end = self._virtual_window_range
        self._update_virtual_spacers(start, end, len(self._items))
        if anchor is not None:
            self._virtual_scroll_to_anchor(*anchor)
        # The newly measured heights can change which rows are in the
        # viewport.  Reconcile once on idle instead of rebuilding recursively.
        if self._virtual_visible_range(len(self._items)) != self._virtual_window_range:
            self._schedule_virtual_window_sync()

    def _render_rows(self):
        if self._destroyed or self._body is None:
            return
        try:
            if not self._body.winfo_exists():
                return
        except tk.TclError:
            return
        if self._selected_idx is not None and self._selected_idx >= len(self._items):
            self._selected_idx = None
        self._update_action_toolbar()
        self._cancel_after_id("_row_render_after_id")
        self._cancel_after_id("_refresh_after_id")
        self._cancel_after_id("_restore_scroll_after_id")
        self._cancel_after_id("_virtual_window_after_id")
        self._scroll_restore_generation += 1
        self._row_render_generation += 1
        generation = self._row_render_generation
        self._rendering = True
        self._virtualized = len(self._items) > self.VIRTUALIZE_THRESHOLD
        self._virtual_window_range = (0, 0)
        self._width_refresh_pending = True
        self._row_widths_dirty = True
        self._content_min_widths_cache = None
        self._virtual_height_cache = {}
        self._virtual_prefix_cache = None
        old_body = self._body
        try:
            old_children = old_body.winfo_children()
        except tk.TclError:
            old_children = []

        # Swap in an empty body first. Destroying thousands of old rows is
        # then performed in small batches without blocking the new refresh.
        if old_children and self._canvas is not None and self._body_window_id is not None:
            new_body = tk.Frame(self._canvas, bg="white")
            new_body.bind("<Configure>", self._on_body_configure)
            self._body = new_body
            try:
                self._canvas.itemconfigure(self._body_window_id, window=new_body)
            except tk.TclError:
                try:
                    new_body.destroy()
                except tk.TclError:
                    pass
                self._body = old_body
                self._rendering = False
                return
            self._retired_bodies.append(old_body)
            self._schedule_retired_body_cleanup()
        self._row_frames.clear()
        self._row_widgets.clear()
        self._row_indices.clear()
        render_body = self._body
        render_items = tuple(self._items)

        if self._virtualized:
            self._prepare_virtual_body(render_body)
            self._render_virtual_window(render_items, generation)
            return

        def append_batch(start: int) -> None:
            if (
                self._destroyed
                or generation != self._row_render_generation
                or self._body is not render_body
            ):
                return
            try:
                if not render_body.winfo_exists():
                    return
            except tk.TclError:
                return
            self._row_render_after_id = None
            end = min(start + self.RENDER_BATCH_SIZE, len(render_items))
            for i in range(start, end):
                item = render_items[i]
                row_frame = tk.Frame(
                    render_body, bg="white", highlightthickness=0, bd=0,
                    takefocus=True,
                )
                row_frame.pack(fill=tk.X, anchor="w")
                widgets = self._create_row_widgets(row_frame, i, item)
                # 操作列：若子类未提供 "操作" key，基类自动补
                if self._action_col is not None and self._action_col not in widgets:
                    action_col_idx = self._columns.index(self._action_col)
                    widgets[self._action_col] = self._create_action_cell(
                        row_frame, i, action_col_idx
                    )
                self._row_frames.append(row_frame)
                self._row_widgets.append(widgets)
                self._row_indices.append(i)
                self._apply_row_bg(i)

            if end < len(render_items):
                self._row_render_after_id = self.after(
                    self.RENDER_BATCH_DELAY_MS,
                    lambda next_start=end: append_batch(next_start),
                )
                return

            if generation != self._row_render_generation or self._body is not render_body:
                return
            self._cancel_after_id("_refresh_after_id")
            self._rendering = False
            self._refresh_widths()
            self._schedule_body_window_sync()

        append_batch(0)

    def _schedule_retired_body_cleanup(self) -> None:
        if self._destroyed or not self._retired_bodies:
            return
        if self._retired_body_cleanup_after_id is None:
            self._retired_body_cleanup_after_id = self.after(
                self.RENDER_BATCH_DELAY_MS, self._cleanup_retired_body_batch
            )

    def _cleanup_retired_body_batch(self) -> None:
        self._retired_body_cleanup_after_id = None
        if self._destroyed:
            return
        while self._retired_bodies:
            body = self._retired_bodies[0]
            try:
                children = body.winfo_children()
            except tk.TclError:
                self._retired_bodies.pop(0)
                continue
            for child in children[: self.RENDER_BATCH_SIZE]:
                try:
                    child.destroy()
                except tk.TclError:
                    pass
            try:
                if not body.winfo_children():
                    body.destroy()
                    self._retired_bodies.pop(0)
            except tk.TclError:
                self._retired_bodies.pop(0)
            break
        self._schedule_retired_body_cleanup()

    # ── 列宽 ──

    def _refresh_widths(self):
        if self._destroyed or not self._header or not self._body:
            return
        if self._rendering or self._row_render_after_id is not None:
            self._width_refresh_pending = True
            return
        self._width_refresh_pending = False
        total_w = self._table_viewport_width()
        specs = self._column_specs()
        visible_specs = [spec for spec in specs if spec.key not in self._hidden_cols]
        visible_weights = {
            key: value for key, value in self._weights.items()
            if key not in self._hidden_cols
        }
        previous_pixels = self._pixels
        pixels = compute_column_pixels(visible_specs, visible_weights, total_w)
        pixels.update({col: 0 for col in self._hidden_cols if col in self._columns})
        pixels_changed = pixels != previous_pixels
        self._pixels = pixels

        header_pixels = dict(pixels)
        for col in self._hidden_cols:
            header_pixels[col] = 0
        self._header.refresh_widths(header_pixels)
        for col in self._columns:
            cell = self._header._cells.get(col)
            if cell is not None:
                if col in self._hidden_cols:
                    cell.grid_remove()
                else:
                    cell.grid()

        if pixels_changed or self._row_widths_dirty:
            self._apply_row_pixels(pixels)

    def _apply_row_pixels(self, pixels: dict[str, int]) -> None:
        """Apply already calculated widths without recomputing layout."""
        for widgets in self._row_widgets:
            # 找 row_frame：取任意 cell 的 master
            first_cell = next(iter(widgets.values()), None)
            if first_cell is None:
                continue
            row_frame = first_cell.master
            for idx, col in enumerate(self._columns):
                px = 0 if col in self._hidden_cols else pixels[col]
                row_frame.grid_columnconfigure(idx, minsize=px)
            for wrap_col in self._wrap_cols:
                w = widgets.get(wrap_col)
                if w is not None and wrap_col not in self._hidden_cols:
                    try:
                        w.config(wraplength=max(pixels[wrap_col] - 16, 8))
                    except tk.TclError:
                        pass
        if self._row_render_after_id is None and not self._rendering:
            self._row_widths_dirty = False

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
                min_width=self._column_min_widths.get(col, self._min_width)
                if col not in self._hidden_cols else 0,
                content_min_width=content_mins.get(col, 0),
                resizable=col not in self._hidden_cols,
            )
            for col in self._columns
        ]

    def _measure_column_content_min_widths(self) -> dict[str, int]:
        result: dict[str, int] = {}
        if not self._row_widgets:
            return result
        if self._content_min_widths_cache is not None and self._row_render_after_id is None:
            return dict(self._content_min_widths_cache)
        if self._action_col is not None:
            action_widths = []
            for widgets in self._row_widgets:
                cell = widgets.get(self._action_col)
                if cell is not None:
                    action_widths.append(max(int(cell.winfo_reqwidth()), 1))
            if action_widths:
                result[self._action_col] = max(action_widths)
        if self._row_render_after_id is None:
            self._content_min_widths_cache = dict(result)
        return result

    def _on_resize(self, event=None):
        if self._destroyed:
            return
        self._cancel_after_id("_refresh_after_id")
        self._refresh_after_id = self.after(50, self._run_scheduled_refresh)

    def set_weights(self, weights: dict) -> None:
        """外部设置列宽权重。原样存，由 _refresh_widths 内部 weights_to_pixels 归一化。"""
        self._weights = dict(weights)
        self._width_refresh_pending = True
        self._cancel_after_id("_refresh_after_id")
        if not self._rendering and self._row_render_after_id is None:
            self._refresh_widths()

    def get_weights(self) -> dict:
        """返回当前权重（与 set_weights 写入的一致；可能未归一化）。"""
        return dict(self._weights)

    def set_hidden_cols(self, hidden_cols: list[str]) -> None:
        self._hidden_cols = set(hidden_cols)
        self._render_rows()

    # ── 列宽拖拽 ──

    def _on_drag_start(self, col_idx: int, event):
        self._drag_col_idx = col_idx
        self._drag_start_x_root = event.x_root
        col = self._columns[col_idx]
        self._drag_start_width = self._pixels.get(col, 100)
        self._drag_start_pixels = dict(self._pixels)
        self._unbind_drag_events()
        # 用 bind_all：拖到行/列上时事件目标是子 widget，
        # self 不在子 widget 的 bindtags 链里，self.bind 不会触发。
        self._unbind_drag_events()
        for sequence, callback in (
            ("<B1-Motion>", self._on_drag_motion),
            ("<ButtonRelease-1>", self._on_drag_release),
        ):
            funcid = self.bind_all(sequence, callback, add="+")
            if funcid:
                self._drag_bind_ids[sequence] = funcid

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
        self._row_widths_dirty = True
        if self._drag_row_refresh_after_id is None:
            self._drag_row_refresh_after_id = self.after(
                16, self._apply_scheduled_drag_widths
            )

    def _apply_scheduled_drag_widths(self) -> None:
        self._drag_row_refresh_after_id = None
        if self._rendering or self._row_render_after_id is not None:
            self._width_refresh_pending = True
            return
        if self._row_widgets:
            self._apply_row_pixels(self._pixels)

    def _on_drag_release(self, event):
        # 守卫：没在拖时收到 release 也要清理 binding
        if self._drag_col_idx is None:
            self._unbind_drag_events()
            return
        col_idx = self._drag_col_idx
        col = self._columns[col_idx]
        self._drag_col_idx = None
        self._unbind_drag_events()
        self._cancel_after_id("_drag_row_refresh_after_id")
        self._apply_row_pixels(self._pixels)
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

    def _unbind_drag_events(self) -> None:
        for sequence, funcid in list(self._drag_bind_ids.items()):
            try:
                self.unbind_all(sequence, funcid)
            except (tk.TclError, AttributeError):
                pass
        self._drag_bind_ids.clear()

    # ── 数据 ──

    def refresh_items(self, items: list) -> None:
        """数据刷新入口：行数不变且非虚拟化时复用行增量更新，否则全量重建。

        增量路径跳过销毁/重建/列宽重测，保持选中与滚动位置不变。要求子类
        实现了 _update_row_widgets，否则退化到 _render_rows 保证内容正确。
        """
        if self._destroyed or self._body is None:
            return
        try:
            if not self._body.winfo_exists():
                return
        except tk.TclError:
            return
        new_items = list(items)
        can_incremental = (
            self._row_frames
            and not self._virtualized
            and len(new_items) == len(self._row_frames)
            and type(self)._update_row_widgets is not ListViewBase._update_row_widgets
        )
        self._items = new_items
        # 选中行越界则清空
        if self._selected_idx is not None and self._selected_idx >= len(self._items):
            self._selected_idx = None
        self._update_action_toolbar()
        if not can_incremental:
            self._render_rows()
            return
        # 取消进行中的重建任务，递增 generation 使旧批次失效
        self._cancel_after_id("_row_render_after_id")
        self._cancel_after_id("_refresh_after_id")
        self._cancel_after_id("_virtual_window_after_id")
        self._row_render_generation += 1
        self._rendering = False
        for position, item in enumerate(self._items):
            self._update_row_widgets(self._row_widgets[position], position, item)
            self._apply_row_bg(position)

    def set_items(self, items: list) -> None:
        """设置数据列表。"""
        self.refresh_items(items)

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
        for position, row_frame in enumerate(self._row_frames):
            idx = self._row_indices[position] if self._virtualized else position
            try:
                item_id = item_id_getter(idx, self._items[idx])
            except (IndexError, TypeError):
                item_id = item_id_getter(idx)
            if item_id is None:
                continue
            top = int(row_frame.winfo_y())
            if self._virtualized and self._virtual_top_spacer is not None:
                try:
                    top += int(self._virtual_top_spacer.winfo_height())
                except tk.TclError:
                    pass
            rows.append(RowGeometry(
                item_id=str(item_id),
                top=top,
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
        if anchor is None or not self._canvas:
            return

        if self._virtualized:
            target_id = str(anchor.item_id if isinstance(anchor, ScrollAnchor) else anchor.get("item_id", ""))
            target_index = None
            for idx, item in enumerate(self._items):
                try:
                    item_id = item_id_getter(idx, item)
                except TypeError:
                    item_id = item_id_getter(idx)
                if item_id is not None and str(item_id) == target_id:
                    target_index = idx
                    break
            if target_index is not None:
                offset_ratio = anchor.offset_ratio if isinstance(anchor, ScrollAnchor) else anchor.get("offset_ratio", 0.0)
                self.scroll_to_index(target_index, offset_ratio)
            return

        self._cancel_after_id("_restore_scroll_after_id")
        self._scroll_restore_generation += 1
        restore_generation = self._scroll_restore_generation

        def do_scroll(previous_signature=None, attempts_left: int = 8):
            self._restore_scroll_after_id = None
            if restore_generation != self._scroll_restore_generation:
                return
            if not self._canvas:
                return
            try:
                if not self.winfo_exists():
                    return
            except tk.TclError:
                return
            if not self._row_frames:
                if self._row_render_after_id is not None and attempts_left > 0:
                    self._restore_scroll_after_id = self.after(
                        50, lambda: do_scroll(previous_signature, attempts_left - 1)
                    )
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
                    self._restore_scroll_after_id = self.after(
                        50, lambda: do_scroll(current_signature, attempts_left - 1)
                    )
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
                    self._restore_scroll_after_id = self.after(
                        50, lambda: do_scroll(None, attempts_left - 1)
                    )
            finally:
                self._restoring_scroll = False

        self._restore_scroll_after_id = self.after(50, do_scroll)

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
        if self._virtualized and self._canvas and self._items:
            try:
                viewport = max(int(self._canvas.winfo_height()), self.VIRTUAL_ROW_HEIGHT)
                prefix = self._virtual_height_prefix()
                idx = min(max(int(idx), 0), len(self._items) - 1)
                target = max(prefix[idx] - int(viewport * offset_ratio), 0)
                target = min(target, max(prefix[-1] - viewport, 1))
                self._canvas.yview_moveto(max(0.0, min(1.0, target / max(prefix[-1], 1))))
                self._virtual_window_range = (0, 0)
                self._render_virtual_window(tuple(self._items), self._row_render_generation)
            except tk.TclError:
                pass
            return
        anchor = ScrollAnchor(item_id=str(idx), offset_ratio=offset_ratio, fallback_index=idx)
        self.restore_scroll_anchor(anchor, lambda row_idx, item=None: row_idx)

    # ── 行选中 ──

    def get_selected_index(self) -> int | None:
        """返回当前选中行索引（按当前 items 列表），无选中返回 None。"""
        return self._selected_idx

    def _visible_row_position(self, idx: int) -> int | None:
        if self._virtualized:
            try:
                return self._row_indices.index(idx)
            except ValueError:
                return None
        if 0 <= idx < len(self._row_frames):
            return idx
        return None

    def _get_row_frame(self, idx: int) -> tk.Frame | None:
        position = self._visible_row_position(idx)
        if position is None:
            return None
        return self._row_frames[position]

    def _get_row_widgets(self, idx: int) -> dict | None:
        position = self._visible_row_position(idx)
        if position is None:
            return None
        return self._row_widgets[position]

    def _ensure_virtual_index_visible(self, idx: int) -> None:
        if not self._virtualized or not self._canvas or not self._items:
            return
        try:
            top = max(int(self._canvas.canvasy(0)), 0)
            viewport = max(int(self._canvas.winfo_height()), self.VIRTUAL_ROW_HEIGHT)
            prefix = self._virtual_height_prefix()
            idx = min(max(int(idx), 0), len(self._items) - 1)
            item_top = prefix[idx]
            item_bottom = prefix[idx + 1]
            if item_top < top:
                target = item_top
            elif item_bottom > top + viewport:
                target = item_bottom - viewport
            else:
                return
            target = min(target, max(prefix[-1] - viewport, 1))
            self._canvas.yview_moveto(max(0.0, min(1.0, target / max(prefix[-1], 1))))
            self._virtual_window_range = (0, 0)
            self._render_virtual_window(tuple(self._items), self._row_render_generation)
        except tk.TclError:
            return

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
            self._ensure_virtual_index_visible(idx)
            self._apply_row_bg(idx)
        self._update_action_toolbar()

    def set_header_sort_indicator(self, col: str, direction: str | None) -> None:
        """设置排序列头箭头指示。"""
        if self._header is not None:
            self._header.set_sort_indicator(col, direction)

    def _on_row_click(self, idx: int) -> None:
        """用户点数据单元 → 选中并高亮，再次点击取消选中。"""
        self.set_selected_index(idx)
        # 让该行获焦
        rf = self._get_row_frame(idx)
        if rf is not None:
            try:
                rf.config(takefocus=True)
                rf.focus_set()
            except Exception:
                pass

    def _apply_row_bg(self, idx: int) -> None:
        """设置单行的背景色（含直接子 widget）。"""
        if idx < 0 or idx >= len(self._items):
            return
        if idx == self._selected_idx:
            bg = self._selection_bg
        elif self._row_bg_getter is not None:
            bg = self._row_bg_getter(idx, self._items[idx])
        else:
            bg = ROW_STRIPE if idx % 2 == 1 else "white"
        rf = self._get_row_frame(idx)
        if rf is None:
            return
        rf.config(bg=bg)
        for w in rf.winfo_children():
            self._apply_widget_bg(w, bg)

    @staticmethod
    def _apply_widget_bg(widget, bg: str) -> None:
        try:
            widget.config(bg=bg)
        except (tk.TclError, AttributeError):
            pass
        try:
            children = widget.winfo_children()
        except (tk.TclError, AttributeError):
            return
        for child in children:
            ListViewBase._apply_widget_bg(child, bg)

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
        for position, rf in enumerate(self._row_frames):
            try:
                top = rf.winfo_rooty()
                bot = top + rf.winfo_height()
            except Exception:
                continue
            if top <= y_root <= bot:
                return self._row_indices[position] if self._virtualized else position
        return None

    def _fire_row_right_click(self, event, idx: int) -> None:
        """每个 cell 在 _create_row_widgets 里 bind：用户右键 cell → 触发本方法。

        统一走 _on_row_right_click（子类重写）。
        """
        # 同步选中该行
        self.set_selected_index(idx)
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
        for position, rf in enumerate(self._row_frames):
            top = rf.winfo_rooty()
            height = max(rf.winfo_height(), 1)
            if y_root < top + height / 2:
                return self._row_indices[position] if self._virtualized else position
            if y_root < top + height:
                return (self._row_indices[position] + 1) if self._virtualized else position + 1
        if self._virtualized:
            return self._row_indices[-1] + 1
        return len(self._row_frames)

    def _show_insertion_line(self, target_idx: int) -> None:
        line_parent = self._virtual_row_host if self._virtualized else self._body
        if not line_parent:
            return
        self._hide_insertion_line()
        line = tk.Frame(line_parent, bg=ACCENT, height=2)
        if self._virtualized:
            first = self._row_indices[0] if self._row_indices else 0
            last = self._row_indices[-1] + 1 if self._row_indices else 0
            if target_idx <= first:
                before = self._row_frames[0] if self._row_frames else None
                if before:
                    line.pack(fill=tk.X, before=before)
                else:
                    line.pack(fill=tk.X)
            elif target_idx >= last:
                line.pack(fill=tk.X)
            else:
                position = max(target_idx - first, 0)
                line.pack(fill=tk.X, before=self._row_frames[position])
        elif target_idx <= 0:
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

    def destroy(self):
        """Cancel deferred layout/render work before tearing down the view."""
        self._destroyed = True
        toplevel = self._event_toplevel
        _WHEEL_VIEWS.discard(self)
        self._scroll_restore_generation += 1
        self._row_render_generation += 1
        self._rendering = False
        for attr in (
            "_row_render_after_id",
            "_virtual_window_after_id",
            "_refresh_after_id",
            "_drag_row_refresh_after_id",
            "_body_window_sync_after_id",
            "_scroll_save_after_id",
            "_restore_scroll_after_id",
            "_retired_body_cleanup_after_id",
        ):
            self._cancel_after_id(attr)
        self._unbind_drag_events()
        if toplevel is not None:
            for sequence, funcid in self._key_bind_ids:
                try:
                    toplevel.unbind(sequence, funcid)
                except (tk.TclError, AttributeError):
                    pass
        self._key_bind_ids.clear()
        if toplevel is not None:
            _release_wheel_dispatch(toplevel)
        self._event_toplevel = None
        self._hide_insertion_line()
        self._retired_bodies.clear()
        if self._action_menu is not None:
            try:
                self._action_menu.destroy()
            except tk.TclError:
                pass
            self._action_menu = None
        super().destroy()


__all__ = ["ListViewBase"]
