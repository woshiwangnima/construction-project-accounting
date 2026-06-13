"""状态徽章组件：小圆圈图标在上方居中、文字在下方居中"""

import tkinter as tk
from ..theme import APP_BG, FONT_SMALL, FONT_BODY_BOLD
from ...project_status import ProjectStatus


class StatusBadge(tk.Frame):
    """垂直状态展示：上方居中圆圈图标，下方居中文字。"""

    def __init__(self, parent, status=None, *, icon=None, text=None, color=None,
                 font_size=12, bg=None, **kwargs):
        super().__init__(parent, bg=bg or APP_BG, **kwargs)

        if status is not None:
            icon = status.icon
            text = status.display_name
            color = status.color

        icon_lbl = tk.Label(self, text=icon or "", font=(FONT_BODY_BOLD[0], font_size),
                            bg=self["bg"], fg=color, anchor="center")
        icon_lbl.pack()

        text_lbl = tk.Label(self, text=text or "", font=(FONT_SMALL[0], font_size - 2),
                            bg=self["bg"], fg=color, anchor="center")
        text_lbl.pack()

        self._icon_lbl = icon_lbl
        self._text_lbl = text_lbl

    def configure_status(self, status: ProjectStatus):
        icon_lbl = self._icon_lbl
        text_lbl = self._text_lbl
        icon_lbl.config(text=status.icon, fg=status.color)
        text_lbl.config(text=status.display_name, fg=status.color)

    def set_bg(self, color):
        self.config(bg=color)
        for child in self.winfo_children():
            child.config(bg=color)


class ClickableStatusBadge(StatusBadge):
    """可点击的 StatusBadge，点击触发 on_click 回调。"""

    def __init__(self, parent, status=None, *, on_click=None,
                 icon=None, text=None, color=None, font_size=14, bg=None, **kwargs):
        super().__init__(parent, status=status, icon=icon, text=text, color=color,
                         font_size=font_size, bg=bg, **kwargs)

        self._on_click = on_click
        self.config(cursor="hand2")
        for w in [self, self._icon_lbl, self._text_lbl]:
            w.bind("<Button-1>", self._handle_click)

    def _handle_click(self, event=None):
        if self._on_click:
            self._on_click()
