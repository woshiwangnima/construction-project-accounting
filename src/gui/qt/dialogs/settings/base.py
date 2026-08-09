"""设置面板基类与共享控件（Qt）。

面板在切换时保持实例缓存；设置统一在窗口关闭时由 SettingsDialog 依次
调用 save() 落盘，避免切换导航时频繁写文件。
"""
from PySide6.QtWidgets import (
    QColorDialog, QFrame, QHBoxLayout, QLabel, QLineEdit, QPushButton,
    QSizePolicy, QVBoxLayout, QWidget,
)

from ....theme import BORDER, TEXT_PRIMARY, TEXT_SECONDARY


def section_title(text: str) -> QLabel:
    label = QLabel(text)
    label.setStyleSheet("font-size: 16px; font-weight: bold;")
    return label


def section_hint(text: str) -> QLabel:
    label = QLabel(text)
    label.setStyleSheet(f"color: {TEXT_SECONDARY}; font-size: 12px;")
    label.setWordWrap(True)
    return label


def separator() -> QFrame:
    line = QFrame()
    line.setFrameShape(QFrame.HLine)
    line.setStyleSheet(f"color: {BORDER}; background: {BORDER}; max-height: 1px;")
    return line


def normalize_hex_color(value, fallback: str) -> str:
    """返回规范化的 #RRGGBB 颜色；非法值回退 fallback。"""
    text = str(value or "").strip()
    if len(text) == 7 and text.startswith("#"):
        return text.lower()
    return fallback


class ColorField(QWidget):
    """色值编辑框 + 取色按钮的组合控件。"""

    def __init__(self, initial="#ffffff", on_change=None, parent=None):
        super().__init__(parent)
        self._on_change = on_change
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)

        color = normalize_hex_color(initial, "#ffffff")
        self._editor = QLineEdit()
        self._editor.setReadOnly(True)
        self._editor.setText(color)
        self._editor.setFixedWidth(88)
        self._editor.setStyleSheet(
            f"background: {color}; border: 1px solid {BORDER}; border-radius: 6px;"
        )
        layout.addWidget(self._editor)

        pick_btn = QPushButton("选择")
        pick_btn.setProperty("secondary", True)
        pick_btn.clicked.connect(self._pick)
        layout.addWidget(pick_btn)

    def _pick(self) -> None:
        picked = QColorDialog.getColor()
        if picked.isValid():
            self.setText(picked.name())

    def setText(self, text: str) -> None:
        color = normalize_hex_color(text, "")
        if not color:
            return
        self._editor.setText(color)
        self._editor.setStyleSheet(
            f"background: {color}; border: 1px solid {BORDER}; border-radius: 6px;"
        )
        if self._on_change is not None:
            self._on_change(color)

    def text(self) -> str:
        return self._editor.text()


def color_row(
    layout: QVBoxLayout,
    label: str,
    initial: str,
    on_change=None,
) -> ColorField:
    """一行：标签 + ColorField。颜色变化时回调 on_change(hex)。"""
    row = QHBoxLayout()
    row.setSpacing(8)
    name = QLabel(label)
    name.setStyleSheet(f"color: {TEXT_PRIMARY};")
    name.setFixedWidth(90)
    row.addWidget(name)
    field = ColorField(initial, on_change=on_change)
    row.addWidget(field)
    row.addStretch(1)
    layout.addLayout(row)
    return field


class BasePanel(QWidget):
    """设置面板基类：标题 + 提示 + 内容容器 + load()/save() 钩子。"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("settingsPanel")
        self.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Maximum)
        self._layout = QVBoxLayout(self)
        self._layout.setContentsMargins(24, 20, 28, 24)
        self._layout.setSpacing(12)

        self._layout.addWidget(section_title(self.title_text()))
        hint = self.hint_text()
        if hint:
            self._layout.addWidget(section_hint(hint))

        self._body = QWidget()
        self._body_layout = QVBoxLayout(self._body)
        self._body_layout.setContentsMargins(0, 6, 0, 0)
        self._body_layout.setSpacing(10)
        self._layout.addWidget(self._body)
        self.build(self._body_layout)
        try:
            self.load()
        except NotImplementedError:
            pass

    # ── 子类接口 ───────────────────────────────────────────────────────

    def title_text(self) -> str:
        raise NotImplementedError

    def hint_text(self) -> str:
        return ""

    def build(self, layout: QVBoxLayout) -> None:
        raise NotImplementedError

    def load(self) -> None:
        """从配置读取当前值填充控件；面板构建后自动调用。"""
        raise NotImplementedError

    def save(self) -> None:
        """把面板当前值写回配置；关闭窗口时统一调用。"""
        raise NotImplementedError
