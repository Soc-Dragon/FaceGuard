"""离开检测：连续无脸 -> 锁屏 -> 休眠。"""

from __future__ import annotations

import logging
import time

from . import locker

log = logging.getLogger("faceguard.presence")


def _num(v, default):
    """取数值，非法返回 default。"""
    return v if isinstance(v, (int, float)) and not isinstance(v, bool) and v > 0 else default


class Presence:
    """用户在岗 / 离开状态机。"""

    def __init__(self, cfg: dict):
        pcfg = cfg.get("presence", {})
        self.enabled = pcfg.get("enabled", True)
        self.no_face_threshold = _num(pcfg.get("no_face_threshold_seconds"), 10)
        self.lock_after = _num(pcfg.get("absence_lock_seconds"), 300)
        self.sleep_after = _num(pcfg.get("sleep_after_seconds"), 300)

        self._last_seen = time.time()
        self._locked_at: float | None = None
        self._state = "present"  # present | away | locked | sleeping

    def update(self, faces_present: bool, cfg: dict) -> str:
        """根据当前是否有人脸，推进状态机，返回当前状态。"""
        if not self.enabled:
            return "present"
        now = time.time()
        pcfg = cfg.get("presence", {})
        self.lock_after = _num(pcfg.get("absence_lock_seconds"), self.lock_after)
        self.sleep_after = _num(pcfg.get("sleep_after_seconds"), self.sleep_after)
        self.no_face_threshold = _num(pcfg.get("no_face_threshold_seconds"), self.no_face_threshold)

        if faces_present:
            self._last_seen = now
            if self._state in ("away", "locked"):
                log.info("用户回归，恢复正常。")
            self._state = "present"
            self._locked_at = None
            return self._state

        # 无人脸
        away_for = max(0, now - self._last_seen)
        if away_for < self.no_face_threshold:
            return self._state  # 仍在容忍期

        if self._state == "present":
            log.info("用户离开，进入 away 状态。")
            self._state = "away"

        if self._state == "away" and away_for >= self.lock_after:
            log.info("离开 %ds，执行锁屏。", int(away_for))
            if locker.lock_workstation():
                self._locked_at = now
                self._state = "locked"
            else:
                log.warning("锁屏失败，保持 away 状态。")
            return self._state

        if self._state == "locked" and self._locked_at is not None:
            locked_for = now - self._locked_at
            if locked_for >= self.sleep_after:
                log.info("锁屏 %ds 未解锁，执行休眠。", int(locked_for))
                if locker.suspend(sleep=True):
                    self._state = "sleeping"
                    self._locked_at = None
                else:
                    log.warning("休眠失败，保持 locked 状态。")
            return self._state

        return self._state
