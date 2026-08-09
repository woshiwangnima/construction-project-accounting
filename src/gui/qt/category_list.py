"""Qt 分类主-从窗格：左侧分类列表（替代 Tk 自绘 category 行）。

一行一个分类：名称 + "N项" 徽标 + 选中高亮（HIGHLIGHT_BG 底色 / ACCENT 指示条）。
内置右键菜单：添加分类 / 上移 / 下移 / 编辑分类 / 删除分类。
"""
from qtawesome import icon as qta_icon
from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtWidgets import (
    QAbstractItemView, QHBoxLayout, QLabel, QListWidget, QListWidgetItem,
    QMenu, QSizePolicy, QVBoxLayout, QWidget,
)

from ..font_manager import font_manager
from ..theme import (
    ACCENT, APP_BG, HIGHLIGHT_BG, ROW_HOVER, SEPARATOR,
    TEXT_PRIMARY, TEXT_SECONDARY,
)

ROW_HEIGHT = 38

_ACTION_LABELS = {
    "add": "添加分类",
    "up": "上移",
    "down": "下移",
    "edit": "编辑分类",
    "delete": "删除分类",
}

_ACTION_ICONS = {
    "add": "fa5s.folder-plus",
    "up": "fa5s.arrow-up",
    "down": "fa5s.arrow-down",
    "edit": "fa5s.edit",
    "delete": "fa5s.trash-alt",
}

# 仅保留全局 QSS 未覆盖的必要项：选中态保持透明，
# 由行 widget（_CategoryRow）自绘高亮，避免双重底色冲突。
_LIST_QSS = "QListWidget::item:selected { background: transparent; }"


class _CategoryRow(QWidget):
    """单行：ACCENT 指示条 + 名称 + 计数徽标。"""

    def __init__(self, name: str, count: int, selected: bool,
                 on_press=None, on_context=None, parent=None):
        super().__init__(parent)
        self._name = name
        self._count = count
        self._selected = selected
        self._hover = False
        self._on_press = on_press
        self._on_context = on_context

        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 0, 10, 0)
        layout.setSpacing(8)
        self._indicator = QLabel(self)
        self._indicator.setFixedWidth(3)
        self._indicator.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Expanding)
        layout.addWidget(self._indicator)
        self._name_lbl = QLabel(name, self)
        self._name_lbl.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        layout.addWidget(self._name_lbl, 1)
        self._count_lbl = QLabel(f"{count}项", self)
        layout.addWidget(self._count_lbl)
        self._apply_style()

    def set_count(self, count: int) -> None:
        self._count = count
        self._count_lbl.setText(f"{count}项")

    def set_selected(self, selected: bool) -> None:
        self._selected = selected
        self._apply_style()

    def set_hover(self, hover: bool) -> None:
        self._hover = hover
        self._apply_style()

    def apply_fonts(self) -> None:
        self._apply_style()

    def _apply_style(self) -> None:
        bg = HIGHLIGHT_BG if self._selected else (ROW_HOVER if self._hover else APP_BG)
        fg = ACCENT if self._selected else TEXT_PRIMARY
        self.setStyleSheet(f"background: {bg}; border: none; border-radius: 6px;")
        self._indicator.setStyleSheet(
            f"background: {ACCENT if self._selected else 'transparent'};"
        )
        self._name_lbl.setFont(
            font_manager.get("tree_header") if self._selected
            else font_manager.get("tree")
        )
        self._name_lbl.setStyleSheet(
            f"color: {fg}; background: transparent; border: none;"
        )
        self._count_lbl.setFont(font_manager.get("small"))
        self._count_lbl.setStyleSheet(
            f"color: {TEXT_SECONDARY}; background: transparent; border: none;"
        )

    def enterEvent(self, event) -> None:
        self.set_hover(True)
        super().enterEvent(event)

    def leaveEvent(self, event) -> None:
        self.set_hover(False)
        super().leaveEvent(event)

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.LeftButton and self._on_press is not None:
            self._on_press()
            event.accept()
        elif event.button() == Qt.RightButton and self._on_context is not None:
            self._on_context(event.globalPos())
            event.accept()
        else:
            super().mousePressEvent(event)


class QtCategoryList(QWidget):
    """分类列表控件：名称 + 计数徽标 + 选中高亮 + 右键菜单。"""

    category_selected = Signal(str)
    menu_action = Signal(str, str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("categoryList")
        self.setStyleSheet(
            f"#categoryList {{ background: {APP_BG};"
            f" border-right: 1px solid {SEPARATOR}; }}"
        )
        self._names: list[str] = []
        self._counts: dict[str, int] = {}
        self._selected: str | None = None
        self._editable = True
        self._updating = False
        self._rows: dict[str, _CategoryRow] = {}
        self._item_by_name: dict[str, QListWidgetItem] = {}

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)

        self._header = QLabel("分类列表", self)
        self._header.setFont(font_manager.get("subheading"))
        self._header.setStyleSheet(f"color: {TEXT_PRIMARY}; border: none;")
        layout.addWidget(self._header)

        self._list = QListWidget(self)
        self._list.setStyleSheet(_LIST_QSS)
        self._list.setSelectionMode(QAbstractItemView.SingleSelection)
        self._list.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self._list.setVerticalScrollMode(QAbstractItemView.ScrollPerPixel)
        self._list.setSpacing(2)
        self._list.itemSelectionChanged.connect(self._on_selection_changed)
        self._list.setContextMenuPolicy(Qt.CustomContextMenu)
        self._list.customContextMenuRequested.connect(self._on_context_requested)
        layout.addWidget(self._list, 1)

    # ── 公共接口 ────────────────────────────────────────────────────────────

    def set_categories(self, categories: dict[str, int]) -> None:
        """全量设置分类（名称->计数，dict 顺序即显示顺序）。保持选中，失效则清空。"""
        names = list(categories.keys())
        if names == self._names:
            self._counts = dict(categories)
            self._update_counts()
            return
        self._names = names
        self._counts = dict(categories)
        self._rebuild()

    def update_counts(self, counts: dict[str, int]) -> None:
        """仅刷新各分类的计数徽标（不改列表结构/选中）。"""
        self._counts = dict(counts)
        self._update_counts()

    def set_selected(self, name: str | None) -> None:
        """程序化选中（不触发 category_selected 信号）。"""
        self._updating = True
        try:
            self._selected = name
            if name is None:
                self._list.clearSelection()
            else:
                item = self._item_by_name.get(name)
                if item is not None:
                    self._list.setCurrentItem(item)
        finally:
            self._updating = False
        self._restyle()

    def get_selected(self) -> str | None:
        return self._selected

    def set_editable(self, editable: bool) -> None:
        self._editable = editable

    def refresh_fonts(self) -> None:
        self._header.setFont(font_manager.get("subheading"))
        for row in self._rows.values():
            row.apply_fonts()

    # ── 内部 ────────────────────────────────────────────────────────────────

    def _rebuild(self) -> None:
        self._list.blockSignals(True)
        self._list.clear()
        self._rows.clear()
        self._item_by_name.clear()
        for name in self._names:
            self._add_row(name, self._counts.get(name, 0))
        self._list.blockSignals(False)
        if self._selected is not None and self._selected not in self._item_by_name:
            self._selected = None
        self._restyle()

    def _add_row(self, name: str, count: int) -> None:
        item = QListWidgetItem()
        item.setSizeHint(QSize(0, ROW_HEIGHT))
        item.setData(Qt.UserRole, name)
        row = _CategoryRow(
            name, count, name == self._selected,
            on_press=lambda n=name: self._select_item(n),
            on_context=lambda pos, n=name: self._show_menu(n, pos),
        )
        self._rows[name] = row
        self._item_by_name[name] = item
        self._list.addItem(item)
        self._list.setItemWidget(item, row)

    def _update_counts(self) -> None:
        for name, row in self._rows.items():
            row.set_count(self._counts.get(name, 0))

    def _restyle(self) -> None:
        for name, row in self._rows.items():
            row.set_selected(name == self._selected)

    def _select_item(self, name: str) -> None:
        if name == self._selected:
            return
        self._updating = True
        try:
            self._selected = name
            item = self._item_by_name.get(name)
            if item is not None:
                self._list.setCurrentItem(item)
        finally:
            self._updating = False
        self._restyle()
        self.category_selected.emit(name)

    def _on_selection_changed(self) -> None:
        if self._updating:
            return
        items = self._list.selectedItems()
        if not items:
            return
        name = items[0].data(Qt.UserRole)
        if name and name != self._selected:
            self._selected = name
            self._restyle()
            self.category_selected.emit(name)

    def _on_context_requested(self, pos) -> None:
        item = self._list.itemAt(pos)
        global_pos = self._list.viewport().mapToGlobal(pos)
        if item is None:
            self._show_empty_menu(global_pos)
            return
        self._show_menu(item.data(Qt.UserRole), global_pos)

    def _show_empty_menu(self, global_pos) -> None:
        menu = QMenu(self)
        self._add_menu_action(menu, "add", "", True)
        menu.exec(global_pos)

    def _show_menu(self, name: str, global_pos) -> None:
        idx = self._names.index(name) if name in self._names else -1
        last = len(self._names) - 1
        menu = QMenu(self)
        self._add_menu_action(menu, "add", name, True)
        menu.addSeparator()
        self._add_menu_action(menu, "up", name, idx > 0)
        self._add_menu_action(menu, "down", name, 0 <= idx < last)
        menu.addSeparator()
        self._add_menu_action(menu, "edit", name, True)
        menu.addSeparator()
        self._add_menu_action(menu, "delete", name, True)
        menu.exec(global_pos)

    def _add_menu_action(self, menu: QMenu, action: str, name: str, enabled: bool) -> None:
        entry = menu.addAction(
            qta_icon(_ACTION_ICONS[action]),
            _ACTION_LABELS[action],
            lambda: self.menu_action.emit(name, action),
        )
        entry.setEnabled(enabled and self._editable)
