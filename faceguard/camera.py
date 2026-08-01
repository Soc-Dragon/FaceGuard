"""摄像头捕获管理：单例 VideoCapture，带重连与帧节流。"""

from __future__ import annotations

import logging
import time

import cv2

log = logging.getLogger("faceguard.camera")


class Camera:
    """线程安全的摄像头封装（在调用线程内顺序读帧）。"""

    def __init__(self, index: int = 0, width: int = 640, height: int = 480, fps: int = 15):
        self.index = index
        self.width = width
        self.height = height
        self.fps = fps
        self.cap: cv2.VideoCapture | None = None
        self._frame_interval = 1.0 / fps if fps > 0 else 0.0
        self._last_read = 0.0

    def open(self) -> bool:
        """打开摄像头，失败则自动尝试其它后端。"""
        for backend in (cv2.CAP_DSHOW, cv2.CAP_MSMF, cv2.CAP_ANY):
            self.cap = cv2.VideoCapture(self.index, backend)
            if self.cap and self.cap.isOpened():
                break
        if not self.cap or not self.cap.isOpened():
            log.error("无法打开摄像头 index=%d", self.index)
            return False
        self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, self.width)
        self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, self.height)
        self.cap.set(cv2.CAP_PROP_FPS, self.fps)
        log.info("摄像头已打开 %dx%d@%dfps", self.width, self.height, self.fps)
        return True

    def read(self):
        """按 fps 节流读帧，返回 (success, frame)。"""
        if not self.cap or not self.cap.isOpened():
            return False, None
        now = time.time()
        if self._frame_interval and (now - self._last_read) < self._frame_interval:
            # 跳过过快的读取，但仍要 grab 以清空缓冲
            self.cap.grab()
            return False, None
        self._last_read = now
        for _ in range(3):  # 重试几次
            ok, frame = self.cap.read()
            if ok and frame is not None:
                return True, frame
            time.sleep(0.05)
        return False, None

    def release(self) -> None:
        if self.cap:
            try:
                self.cap.release()
            except Exception:
                pass
            self.cap = None
