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
        self._released = False

    def open(self) -> bool:
        """打开摄像头，失败则自动尝试其它后端。"""
        if self.cap:
            try:
                self.cap.release()
            except Exception:
                pass
            self.cap = None
        for backend in (cv2.CAP_DSHOW, cv2.CAP_MSMF, cv2.CAP_ANY):
            cap = cv2.VideoCapture(self.index, backend)
            if cap and cap.isOpened():
                self.cap = cap
                break
            if cap:
                try:
                    cap.release()
                except Exception:
                    pass
        if not self.cap or not self.cap.isOpened():
            log.error("无法打开摄像头 index=%d", self.index)
            return False
        self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, self.width)
        self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, self.height)
        self.cap.set(cv2.CAP_PROP_FPS, self.fps)
        log.info("摄像头已打开 %dx%d@%dfps", self.width, self.height, self.fps)
        return True

    def read(self):
        """按 fps 节流读帧，返回 (success, frame)。断线自动重连。"""
        try:
            if self._released:
                return False, None
            if not self.cap or not self.cap.isOpened():
                # 断线重连：尝试重新打开
                log.warning("摄像头已断开，尝试重连...")
                if not self.open():
                    return False, None
            now = time.time()
            if self._frame_interval and (now - self._last_read) < self._frame_interval:
                self.cap.grab()
                return False, None
            for _ in range(3):
                ok, frame = self.cap.read()
                if ok and frame is not None:
                    self._last_read = now
                    return True, frame
                time.sleep(0.05)
            # 连续 3 次读失败，释放以便下次重连
            log.warning("摄像头读帧失败，将重连。")
            try:
                self.cap.release()
            except Exception:
                pass
            self.cap = None
            return False, None
        except Exception as e:
            log.warning("摄像头读取异常: %s", e)
            return False, None

    def release(self) -> None:
        if self.cap:
            try:
                self.cap.release()
            except Exception:
                pass
            self.cap = None
        self._released = True
