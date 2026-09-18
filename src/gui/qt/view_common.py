"""内容区共享的卡片/分段容器样式与指标卡工厂（自 content.py 抽出）。"""
from qtawesome import icon as qta_icon

from PySide6.QtCore import QSize, Qt
from PySide6.QtGui import QFont, QFontMetrics
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QVBoxLayout

from ...config_loader import load_app
from ..font_manager import font_manager
from ..theme import CARD_BG, CARD_BORDER, SEGMENT_BG, SYSTEM_GREEN, TEXT_PRIMARY, TEXT_SECONDARY


CARD_QSS = (
    f"background: {CARD_BG}; border: 1px solid {CARD_BORDER};"
    f"border-radius: 8px; padding: 10px 10px;"
)
SEGMENT_QSS = f"background: {SEGMENT_BG}; border-radius: 8px; padding: 2px;"
def _amount_px() -> int:
    """与 theme.build_qss 完全一致的「大数字」像素字号（避免两处口径漂移）。"""
    try:
        base = int(load_app().get("default_font_size", 14))
    except Exception:
        base = 14
    base = max(10, min(30, base))
    return max(base, round(base * 2.0))
def _metric_card_height() -> int:
    """指标卡片的统一高度。

    两个页面（账单 / 工作类型）顶部必须等高，否则切换页签时整块内容会上下跳。
    高度按「大数字」行高推算，因此跟随用户在设置里调整的字号一起缩放。
    """
    font = QFont()
    font.setPixelSize(_amount_px())
    return QFontMetrics(font).height() + 64
def _make_metric_card(icon_name: str, icon_color: str, title: str,
                      value_role: str, value_color: str | None = None,
                      object_name: str = "") -> tuple[QFrame, QLabel]:
    """构建看板指标卡片：左侧图标 + 右侧（标题 / 数值）。

    账单页与工作类型页共用，保证两页顶部骨架的高度与样式完全一致，
    切换页签时不会出现内容整体上跳。
    """
    card = QFrame()
    card.setObjectName("metricCard")
    card.setProperty("card", True)
    # 用 ID 选择器把卡片样式限定在卡片自身：CARD_QSS 的 padding 会沿
    # QSS 级联继承到卡片内的 QLabel，把数值标签凭空撑高 20px。
    card.setStyleSheet(
        f"#metricCard {{ background: {CARD_BG}; border: 1px solid {CARD_BORDER};"
        f" border-radius: 8px; }}"
    )
    card.setFixedHeight(_metric_card_height())
    outer = QHBoxLayout(card)
    outer.setContentsMargins(14, 10, 14, 10)
    outer.setSpacing(12)

    icon = QLabel()
    icon.setStyleSheet("border: none; background: transparent;")
    icon.setPixmap(qta_icon(icon_name, color=icon_color).pixmap(24, 24))
    outer.addWidget(icon, 0, Qt.AlignVCenter)

    box = QVBoxLayout()
    box.setSpacing(2)
    title_lbl = QLabel(title)
    title_lbl.setStyleSheet(
        f"color: {TEXT_SECONDARY}; font-size: 13px; font-weight: bold; border: none;"
    )
    value_lbl = QLabel("")
    if object_name:
        value_lbl.setObjectName(object_name)
    value_lbl.setFont(font_manager.get(value_role))
    prefix = f"color: {value_color}; " if value_color else ""
    value_lbl.setStyleSheet(f"{prefix}font-weight: bold; border: none;")
    # 两端加弹簧，让「标题 + 数值」这组在固定高度里垂直居中，
    # 字号小的卡片（如「未设单价」）不会贴着顶部。
    box.addStretch(1)
    box.addWidget(title_lbl)
    box.addWidget(value_lbl)
    box.addStretch(1)
    outer.addLayout(box, 1)
    return card, value_lbl
def _build_metric_row(specs) -> tuple[QHBoxLayout, dict[str, QLabel]]:
    """按规格批量构建一行指标卡片，返回 (布局, {key: 数值Label})。"""
    row = QHBoxLayout()
    row.setSpacing(12)
    labels: dict[str, QLabel] = {}
    for key, icon, icon_color, title, role, color, obj_name in specs:
        card, value = _make_metric_card(icon, icon_color, title, role, color, obj_name)
        row.addWidget(card, 1)
        labels[key] = value
    return row, labels
