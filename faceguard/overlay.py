"""识别画面可视化叠加：人脸轮廓、关键点、扫描线、置信度、状态文字。

所有特效绘制在摄像头帧上，由 ui.py 显示到屏幕。
"""

from __future__ import annotations

import math
import time

import cv2
import numpy as np


# 配色（BGR）
COLOR_OWNER = (0, 255, 128)      # 本人 - 绿
COLOR_STRANGER = (0, 0, 255)     # 陌生人 - 红
COLOR_INTRUDER = (0, 128, 255)   # 身后入侵 - 橙
COLOR_SCAN = (255, 255, 255)     # 扫描线 - 白
COLOR_TEXT = (255, 255, 255)
COLOR_GLOW = (0, 200, 255)


def draw_face_box(frame, face, label: str, color, confidence: float | None = None,
                  show_conf: bool = True) -> None:
    """绘制人脸框 + 标签。"""
    x, y, w, h = face.x, face.y, face.w, face.h
    # 圆角风格框：四角短线
    corner = max(8, w // 8)
    cv2.line(frame, (x, y), (x + corner, y), color, 2)
    cv2.line(frame, (x, y), (x, y + corner), color, 2)
    cv2.line(frame, (x + w, y), (x + w - corner, y), color, 2)
    cv2.line(frame, (x + w, y), (x + w, y + corner), color, 2)
    cv2.line(frame, (x, y + h), (x + corner, y + h), color, 2)
    cv2.line(frame, (x, y + h), (x, y + h - corner), color, 2)
    cv2.line(frame, (x + w, y + h), (x + w - corner, y + h), color, 2)
    cv2.line(frame, (x + w, y + h), (x + w, y + h - corner), color, 2)

    # 标签条
    text = label
    if show_conf and confidence is not None:
        text += f"  {confidence:.2f}"
    (tw, th), _ = cv2.getTextSize(text, cv2.FONT_HERSHEY_SIMPLEX, 0.5, 1)
    y0 = max(0, y - th - 6)
    cv2.rectangle(frame, (x, y0), (x + tw + 8, y0 + th + 6), color, -1)
    cv2.putText(frame, text, (x + 4, y0 + th + 2),
                cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 0, 0), 1, cv2.LINE_AA)


def draw_landmarks(frame, face, color=COLOR_GLOW) -> None:
    """绘制 5 关键点 + 连接轮廓。"""
    pts = list(face.landmarks.values())
    # 连线：右眼-左眼-鼻-嘴
    pairs = [("right_eye", "left_eye"), ("left_eye", "nose"),
             ("nose", "right_mouth"), ("nose", "left_mouth"),
             ("right_mouth", "left_mouth")]
    for a, b in pairs:
        cv2.line(frame, face.landmarks[a], face.landmarks[b], color, 1, cv2.LINE_AA)
    for p in pts:
        cv2.circle(frame, p, 3, color, -1, cv2.LINE_AA)


def draw_scanline(frame, face, t: float | None = None) -> None:
    """人脸区域内上下扫描线特效。"""
    t = t if t is not None else time.time()
    x, y, w, h = face.x, face.y, face.w, face.h
    # 扫描线位置在人脸框内正弦往返
    progress = (math.sin(t * 2.0) + 1) / 2  # 0..1
    ly = int(y + progress * h)
    overlay = frame.copy()
    cv2.line(overlay, (x, ly), (x + w, ly), COLOR_SCAN, 2, cv2.LINE_AA)
    # 渐变光带
    for d in range(1, 12):
        a = max(0, 80 - d * 7)
        cv2.line(overlay, (x, max(y, ly - d)), (x + w, max(y, ly - d)),
                 (255, 255, 255), 1, cv2.LINE_AA)
    cv2.addWeighted(overlay, 0.35, frame, 0.65, 0, frame)


def draw_glow(frame, face, color=COLOR_GLOW, t: float | None = None) -> None:
    """人脸框外圈呼吸光晕。"""
    t = t if t is not None else time.time()
    x, y, w, h = face.x, face.y, face.w, face.h
    pulse = (math.sin(t * 3.0) + 1) / 2  # 0..1
    alpha = 0.15 + 0.25 * pulse
    pad = 6
    overlay = frame.copy()
    cv2.rectangle(overlay, (x - pad, y - pad), (x + w + pad, y + h + pad),
                  color, -1)
    cv2.addWeighted(overlay, alpha, frame, 1 - alpha, 0, frame)


def draw_status_bar(frame, text: str, color=COLOR_TEXT) -> None:
    """画面底部状态条。"""
    h, w = frame.shape[:2]
    bar_h = 32
    cv2.rectangle(frame, (0, h - bar_h), (w, h), (0, 0, 0), -1)
    cv2.putText(frame, text, (10, h - 10), cv2.FONT_HERSHEY_SIMPLEX,
                0.55, color, 1, cv2.LINE_AA)


def render_overlay(frame, faces, owner_name, confidence, status: str,
                   cfg: dict, t: float | None = None) -> np.ndarray:
    """主渲染入口：在帧上叠加全部特效，返回新帧。"""
    t = t if t is not None else time.time()
    ocfg = cfg.get("overlay", {})
    show_lm = ocfg.get("show_landmarks", True)
    show_scan = ocfg.get("show_scanline", True)
    show_conf = ocfg.get("show_confidence", True)

    for face in faces:
        is_owner = owner_name is not None
        color = COLOR_OWNER if is_owner else COLOR_STRANGER
        label = owner_name if is_owner else "未知"
        if show_scan:
            draw_scanline(frame, face, t)
        draw_glow(frame, face, color, t)
        if show_lm:
            draw_landmarks(frame, face, color)
        draw_face_box(frame, face, label, color,
                      confidence if show_conf else None, show_conf)

    draw_status_bar(frame, status)
    return frame
