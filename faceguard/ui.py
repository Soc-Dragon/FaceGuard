"""识别画面 overlay 窗口：用 tkinter 显示摄像头帧 + 特效。

无边框、置顶、半透明（Windows 上的 -alpha 与 -transparentcolor），
识别成功后可自动隐藏。
"""

from __future__ import annotations

import io
import logging
import threading

import cv2
import numpy as np
from PIL import Image, ImageTk

log = logging.getLogger("faceguard.ui")


class OverlayWindow:
    """tkinter 置顶窗口，显示识别画面。"""

    def __init__(self, title: str = "FaceGuard", width: int = 640, height: int = 480):
        self.width = width
        self.height = height
        self._root = None
        self._label = None
        self._photo = None
        self._lock = threading.Lock()
        self._visible = False
        self._tk_thread = None

    def _build(self):
        import tkinter as tk
        self._root = tk.Tk()
        self._root.title("FaceGuard 识别画面")
        self._root.overrideredirect(True)  # 无边框
        # 居中靠右上
        sw = self._root.winfo_screenwidth()
        self._root.geometry(f"{self.width}x{self.height}+{sw - self.width - 20}+20")
        try:
            self._root.attributes("-topmost", True)
            self._root.attributes("-alpha", 0.95)
        except tk.TclError:
            pass
        self._label = tk.Label(self._root, bg="black")
        self._label.pack(fill="both", expand=True)
        self._root.withdraw()  # 默认隐藏

    def start(self):
        import tkinter as tk
        if self._root is not None:
            return
        self._tk_thread = threading.Thread(target=self._run_tk, daemon=True)
        self._tk_thread.start()

    def _run_tk(self):
        try:
            self._build()
            self._root.mainloop()
        except Exception as e:
            log.error("overlay 窗口异常: %s", e)

    def show(self):
        if self._root is None:
            return
        self._root.after(0, lambda: self._root.deiconify())
        self._visible = True

    def hide(self):
        if self._root is None:
            return
        self._root.after(0, lambda: self._root.withdraw())
        self._visible = False

    def update_frame(self, frame_bgr: np.ndarray):
        """推送一帧到窗口（线程安全）。"""
        if self._root is None or self._label is None:
            return
        try:
            rgb = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB)
            img = Image.fromarray(rgb)
            img = img.resize((self.width, self.height))
            photo = ImageTk.PhotoImage(img)
            def _set():
                self._photo = photo  # 保持引用
                self._label.configure(image=photo)
            self._root.after(0, _set)
        except Exception as e:
            log.debug("overlay 更新失败: %s", e)

    def stop(self):
        if self._root is not None:
            try:
                self._root.after(0, self._root.destroy)
            except Exception:
                pass
            self._root = None
