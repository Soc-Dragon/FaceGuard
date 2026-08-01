"""邮件告警：识别失败时抓拍人脸照片并以附件发送。

使用内置 smtplib + ssl，QQ 邮箱需填授权码（非登录密码）。
"""

from __future__ import annotations

import logging
import smtplib
import ssl
import time
from datetime import datetime
from email.message import EmailMessage
from pathlib import Path

from .config import CAPTURE_DIR

log = logging.getLogger("faceguard.notify")

_last_sent = 0.0


def save_capture(frame, prefix: str = "intruder") -> Path | None:
    """保存一帧抓拍图，返回路径。frame 为 OpenCV BGR 图像。"""
    try:
        import cv2  # 延迟导入，避免非 Windows 环境报错
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        path = CAPTURE_DIR / f"{prefix}_{ts}.jpg"
        cv2.imwrite(str(path), frame, [cv2.IMWRITE_JPEG_QUALITY, 85])
        return path
    except Exception as e:
        log.error("保存抓拍失败: %s", e)
        return None


def send_alert(
    subject: str,
    body: str,
    attachment: Path | None = None,
    cfg: dict | None = None,
) -> bool:
    """发送告警邮件。受 cooldown_seconds 冷却控制。"""
    global _last_sent
    cfg = cfg or {}
    ncfg = cfg.get("notify", {})
    if not ncfg.get("enabled", False):
        return False

    cooldown = ncfg.get("cooldown_seconds", 60)
    now = time.time()
    if now - _last_sent < cooldown:
        log.info("告警冷却中，跳过本次发送。")
        return False

    host = ncfg.get("smtp_host", "smtp.qq.com")
    port = ncfg.get("smtp_port", 465)
    use_ssl = ncfg.get("smtp_ssl", True)
    sender = ncfg.get("sender", "")
    password = ncfg.get("password", "")
    to = ncfg.get("to", sender)

    if not sender or not password:
        log.warning("未配置邮箱授权码，跳过发送。")
        return False

    msg = EmailMessage()
    msg["Subject"] = f"[FaceGuard] {subject}"
    msg["From"] = sender
    msg["To"] = to
    msg.set_content(body + f"\n\n时间: {datetime.now():%Y-%m-%d %H:%M:%S}\n来自 FaceGuard v2.1.0")

    if attachment and Path(attachment).exists():
        data = Path(attachment).read_bytes()
        msg.add_attachment(
            data, maintype="image", subtype="jpeg", filename=Path(attachment).name
        )

    try:
        ctx = ssl.create_default_context()
        if use_ssl:
            with smtplib.SMTP_SSL(host, port, context=ctx, timeout=20) as s:
                s.login(sender, password)
                s.send_message(msg)
        else:
            with smtplib.SMTP(host, port, timeout=20) as s:
                s.starttls(context=ctx)
                s.login(sender, password)
                s.send_message(msg)
        _last_sent = now
        log.info("告警邮件已发送至 %s", to)
        return True
    except Exception as e:
        log.error("邮件发送失败: %s", e)
        return False


def alert_recognition_failed(frame, cfg: dict) -> None:
    """识别失败：保存抓拍 + 发邮件。"""
    cap = save_capture(frame, prefix="failed_unlock")
    send_alert(
        "人脸识别失败告警",
        "检测到陌生人在尝试通过人脸解锁，已抓拍现场照片，请查看附件。",
        attachment=cap,
        cfg=cfg,
    )


def alert_intruder(frame, cfg: dict) -> None:
    """身后出现他人：保存抓拍 + 发邮件。"""
    cap = save_capture(frame, prefix="intruder_behind")
    send_alert(
        "身后出现他人提醒",
        "检测到你身后出现其他人脸，已抓拍现场照片，请查看附件。",
        attachment=cap,
        cfg=cfg,
    )
