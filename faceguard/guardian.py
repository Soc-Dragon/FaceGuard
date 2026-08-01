"""身后入侵守护：画面中出现多张人脸（除本人外还有他人）时告警。"""

from __future__ import annotations

import logging
import time

import cv2

from . import notifier

log = logging.getLogger("faceguard.guardian")


class Guardian:
    """检测身后出现其他人。"""

    def __init__(self, cfg: dict):
        gcfg = cfg.get("guardian", {})
        self.enabled = gcfg.get("enabled", True)
        self.multi_notify = gcfg.get("multi_face_notify", True)
        self.min_area = gcfg.get("min_face_area_ratio", 0.015)
        self.sound = gcfg.get("notify_sound", True)
        self._last_alert = 0.0

    def check(self, frame, faces, owner_name, cfg: dict) -> str | None:
        """返回告警类型 or None。节流期内返回状态但不重复发邮件/响铃。"""
        if not self.enabled:
            return None
        valid = [f for f in faces if f.area_ratio >= self.min_area]
        if len(valid) <= 1:
            return None

        now = time.time()
        # 节流期内：仍处于告警状态，但不重复触发副作用
        if now - self._last_alert < 8:
            return "intruder"

        # 过了节流期，真正触发一次告警
        valid.sort(key=lambda f: f.area_ratio, reverse=True)
        intruders = valid[1:]
        log.warning("检测到身后出现 %d 个他人！", len(intruders))
        if self.sound:
            _beep()
        notifier.alert_intruder(frame, cfg)
        self._last_alert = now  # 只在真正告警时更新，保证节流会过期
        return "intruder"


def _beep():
    """播放系统提示音（Windows）。"""
    try:
        import winsound
        winsound.Beep(2000, 400)
    except Exception:
        pass
