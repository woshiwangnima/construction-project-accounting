"""更新对话框：有新版本时弹出下载确认，含进度条。"""
import queue
import threading
import tkinter as tk
from tkinter import ttk

from ..theme import FONT_BODY, FONT_BUTTON
from ..widgets.confirm_dialog import confirm_dialog
from ...updater import UpdateInfo, UpdateChecker, download_update, apply_update
from ...logger import logger


class UpdateDialog(tk.Toplevel):
    def __init__(self, parent: tk.Widget, info: UpdateInfo):
        super().__init__(parent)
        self.title("发现新版本")
        self.transient(parent)
        self.grab_set()
        self.resizable(False, False)

        self._info = info
        self._downloading = False
        self._progress_queue: queue.Queue = queue.Queue()
        self._download_thread: threading.Thread | None = None
        self._download_result = None

        w, h = 480, 340
        pw = parent.winfo_width() if parent.winfo_width() > 100 else 1280
        ph = parent.winfo_height() if parent.winfo_height() > 100 else 720
        px = parent.winfo_rootx()
        py = parent.winfo_rooty()
        x = px + (pw - w) // 2
        y = py + (ph - h) // 2
        self.geometry(f"{w}x{h}+{x}+{y}")

        self._build_ui()
        self.protocol("WM_DELETE_WINDOW", self._on_cancel)

    def _build_ui(self):
        pad = {"padx": 20, "pady": 6}

        tk.Label(self, text=f"新版本 {self._info.version} 可用", font=FONT_BUTTON).pack(pady=(20, 4), **pad)

        notes = self._info.release_notes or ["（无更新说明）"]
        text_w = tk.Text(self, height=6, wrap=tk.WORD, font=FONT_BODY,
                         relief=tk.FLAT, bg=self.cget("bg"), state=tk.DISABLED)
        text_w.pack(fill=tk.BOTH, **pad)
        text_w.config(state=tk.NORMAL)
        for line in notes:
            text_w.insert(tk.END, f"• {line}\n")
        text_w.config(state=tk.DISABLED)

        self._progress = ttk.Progressbar(self, mode="determinate")
        self._progress.pack(fill=tk.X, **pad)

        self._status_var = tk.StringVar(value="")
        tk.Label(self, textvariable=self._status_var, font=FONT_BODY, fg="#666").pack(**pad)

        btn_frame = tk.Frame(self)
        btn_frame.pack(pady=(0, 16))

        self._download_btn = tk.Button(btn_frame, text="下载更新", font=FONT_BUTTON,
                                       command=self._on_download)
        self._download_btn.pack(side=tk.LEFT, padx=6)
        tk.Button(btn_frame, text="稍后再说", font=FONT_BUTTON,
                  command=self._on_cancel).pack(side=tk.LEFT, padx=6)

    def _on_download(self):
        if self._downloading:
            return
        self._downloading = True
        self._download_btn.config(state=tk.DISABLED, text="正在下载…")
        self._status_var.set("正在下载更新包…")
        self._progress_queue = queue.Queue()
        self._download_result = None
        self.update_idletasks()

        self._download_thread = threading.Thread(
            target=self._download_worker, daemon=True
        )
        self._download_thread.start()
        self._poll_download()

    def _download_worker(self):
        """后台线程：执行下载，将进度放入 queue。"""
        try:
            self._download_result = download_update(
                self._info, self._on_progress_threadsafe
            )
        except Exception as e:
            logger.error("Download thread error: %s", e)
            self._download_result = None

    def _on_progress_threadsafe(self, downloaded: int, total: int):
        """线程安全的进度回调，放入 queue。"""
        self._progress_queue.put((downloaded, total))

    def _poll_download(self):
        """主线程轮询 queue，更新 UI 进度。"""
        try:
            while True:
                downloaded, total = self._progress_queue.get_nowait()
                self._update_progress_ui(downloaded, total)
        except queue.Empty:
            pass

        if self._download_thread is not None and self._download_thread.is_alive():
            self.after(80, self._poll_download)
        else:
            self._on_download_complete(self._download_result)

    def _update_progress_ui(self, downloaded: int, total: int):
        """在主线程更新进度条和状态文本。"""
        if total > 0:
            pct = int(downloaded / total * 100)
            self._progress["value"] = pct
            mb = downloaded / 1024 / 1024
            total_mb = total / 1024 / 1024
            self._status_var.set(f"下载中… {mb:.1f}MB / {total_mb:.1f}MB ({pct}%)")

    def _on_download_complete(self, update_dir):
        """下载完成后在主线程处理后续流程。"""
        if update_dir is None:
            self._status_var.set("下载失败，请检查网络后重试")
            self._download_btn.config(state=tk.NORMAL, text="重试")
            self._downloading = False
            return

        self._status_var.set("下载完成，准备更新…")
        self.update_idletasks()

        confirm = confirm_dialog(
            self, "确认更新",
            "更新包已下载完成。点击「确认」将自动退出程序并应用更新。",
        )
        if not confirm:
            self._status_var.set("已取消，下次启动时再更新")
            self._download_btn.config(state=tk.NORMAL, text="下载更新")
            self._downloading = False
            import shutil
            shutil.rmtree(update_dir, ignore_errors=True)
            return

        apply_update(update_dir)
        self.master.destroy()

    def _on_progress(self, downloaded: int, total: int):
        """保留兼容旧调用，实际由 _on_progress_threadsafe 替代。"""
        pass

    def _on_cancel(self):
        self.grab_release()
        self.destroy()
