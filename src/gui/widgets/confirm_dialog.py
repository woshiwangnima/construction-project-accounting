"""可复用的确认对话框，替代 messagebox.askyesno。

- 字体大小取自 app_config.button_font_size
- 按钮样式与 _make_btn 一致（确认 = danger，取消 = secondary）
- Y/N 快捷键，默认选中取消
"""
import tkinter as tk

from ..theme import APP_BG, ACCENT, ACCENT_HOVER, DANGER, TEXT_PRIMARY
from ...config_loader import load_app


def _mkfont(style: str = "") -> tuple:
    size = (load_app().get("button_font_size") or 16) - 1
    return ("Microsoft YaHei UI", size, style)


def _make_confirm_btn(parent, text, command, bg, fg):
    btn = tk.Button(
        parent, text=text, command=command,
        font=_mkfont("bold"),
        bg=bg, fg=fg,
        activebackground=ACCENT_HOVER, activeforeground="white",
        relief="raised", bd=2, padx=20, pady=10, cursor="hand2",
    )
    btn.bind("<Enter>", lambda e: btn.config(bg=ACCENT_HOVER))
    btn.bind("<Leave>", lambda e: btn.config(bg=bg))
    return btn


def confirm_dialog(parent, title: str, message: str) -> bool:
    result = {"confirmed": False}
    dialog = tk.Toplevel(parent)
    dialog.title(title)
    dialog.transient(parent)
    dialog.grab_set()
    dialog.configure(bg=APP_BG)
    dialog.resizable(False, False)

    font_size = (load_app().get("button_font_size") or 16) - 1
    wraplength = font_size * 36
    msg_label = tk.Label(
        dialog, text=message, font=_mkfont("bold"),
        bg=APP_BG, fg=TEXT_PRIMARY, justify="left", wraplength=wraplength,
    )
    msg_label.pack(anchor="w", padx=24, pady=(20, 4))

    btn_frame = tk.Frame(dialog, bg=APP_BG)
    btn_frame.pack(fill=tk.X, padx=24, pady=(16, 20))

    def confirm():
        result["confirmed"] = True
        dialog.destroy()

    def cancel():
        dialog.destroy()

    confirm_btn = _make_confirm_btn(btn_frame, "确认", confirm, DANGER, "white")
    confirm_btn.pack(side=tk.RIGHT, padx=(8, 0))

    cancel_btn = _make_confirm_btn(btn_frame, "取消", cancel, "#4a5568", "white")
    cancel_btn.pack(side=tk.RIGHT, padx=(8, 0))

    dialog.bind("<KeyPress-y>", lambda e: confirm())
    dialog.bind("<KeyPress-Y>", lambda e: confirm())
    dialog.bind("<KeyPress-n>", lambda e: cancel())
    dialog.bind("<KeyPress-N>", lambda e: cancel())
    dialog.bind("<Escape>", lambda e: cancel())

    dialog.update_idletasks()
    w = max(dialog.winfo_reqwidth(), wraplength + 48)
    h = dialog.winfo_reqheight()
    x = parent.winfo_rootx() + (parent.winfo_width() - w) // 2
    y = parent.winfo_rooty() + (parent.winfo_height() - h) // 2
    dialog.geometry(f"{w}x{h}+{x}+{y}")

    cancel_btn.focus_set()
    parent.wait_window(dialog)
    return result["confirmed"]
