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
        """返回告警类型 or None。"""
        if not self.enabled:
            return None
        # 过滤过小人脸
        valid = [f for f in faces if f.area_ratio >= self.min_area]
        if len(valid) <= 1:
            return None

        # 多张人脸：除最大那张（大概率是本人）外，其余视为入侵
        valid.sort(key=lambda f: f.area_ratio, reverse=True)
        intruders = valid[1:]
        now = time.time()
        if now - self._last_alert < 8:  # 本地节流
            return "intruder"

        log.warning("检测到身后出现 %d 个他人！", len(intruders))
        if self.sound:
            _beep()
        notifier.alert_intruder(frame, cfg)
        self._last_alert = now
        return "intruder"


def _beep():
    """播放系统提示音（Windows）。"""
    try:
        import winsound
        winsound.Beep(2000, 400)
    except Exception:
        pass
