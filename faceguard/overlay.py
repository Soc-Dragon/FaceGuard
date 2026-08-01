"""简洁风格人脸可视化：蓝色激光点阵描绘面部轮廓与五官。

设计：
  · 极简 UI：细线状态栏 + 简洁文字，无花哨玻璃/光晕/粒子
  · 蓝色激光点阵：基于 5 个 landmarks + 人脸框插值生成密集点阵
    - 面部外轮廓（椭圆点阵）
    - 左右眼轮廓（椭圆点阵）
    - 鼻梁（竖线点阵）
    - 嘴唇（椭圆点阵）
    - 眉毛（弧线点阵）
  · 激光质感：中心亮白点 + 外圈蓝色光晕（alpha 叠加）
  · 实时跟随：所有点基于 face.landmarks 动态计算，随人脸变动
全部用 OpenCV 绘制，无外部资源。
"""

from __future__ import annotations

import math
import time

import cv2
import numpy as np


# ---------- 简洁配色（BGR）----------
COLOR_LASER = (255, 140, 0)        # 激光蓝 #008CFF
COLOR_LASER_CORE = (255, 255, 255)  # 激光核心白
COLOR_LASER_DIM = (180, 80, 0)     # 激光蓝暗
COLOR_OWNER = (255, 140, 0)        # 本人 - 蓝
COLOR_STRANGER = (80, 80, 255)     # 陌生人 - 红
COLOR_TEXT = (245, 245, 247)       # Apple 白
COLOR_TEXT_DIM = (160, 160, 170)   # 副文字
COLOR_BG_BAR = (10, 10, 14)        # 状态栏底


# ---------- 激光点阵生成 ----------

def _face_mesh_points(face) -> list[tuple[float, float]]:
    """基于 5 landmarks + 人脸框，生成面部轮廓与五官的密集点阵。

    点阵区域：
      1. 面部外轮廓（椭圆，沿人脸框略内收）
      2. 左右眼轮廓（椭圆）
      3. 鼻梁（眉心→鼻尖竖线）
      4. 嘴唇（横向椭圆）
      5. 眉毛（眼睛上方弧线）
    所有点基于 landmarks 实时计算，随人脸变动而跟随。
    """
    pts: list[tuple[float, float]] = []
    lm = face.landmarks
    le = lm["left_eye"]
    re = lm["right_eye"]
    nose = lm["nose"]
    rm = lm["right_mouth"]
    lm_ = lm["left_mouth"]

    # 瞳距与脸宽参考
    eye_dx = abs(le[0] - re[0])
    eye_dy = abs(le[1] - re[1])
    eye_dist = math.hypot(eye_dx, eye_dy) + 1
    # 眼睛到嘴的距离（脸长参考）
    mouth_cx = (rm[0] + lm_[0]) / 2
    mouth_cy = (rm[1] + lm_[1]) / 2
    face_cx = (le[0] + re[0]) / 2
    face_cy = (le[1] + re[1]) / 2

    # 1. 面部外轮廓（椭圆，基于人脸框）
    rx = face.w * 0.42
    ry = face.h * 0.48
    cx = face.x + face.w / 2
    cy = face.y + face.h / 2 + face.h * 0.02  # 略下移，对齐脸部中心
    for ang in range(0, 360, 6):
        a = math.radians(ang)
        pts.append((cx + rx * math.cos(a), cy + ry * math.sin(a)))

    # 2. 左眼轮廓（椭圆）
    eye_rx = eye_dist * 0.18
    eye_ry = eye_dist * 0.12
    for ang in range(0, 360, 15):
        a = math.radians(ang)
        pts.append((le[0] + eye_rx * math.cos(a), le[1] + eye_ry * math.sin(a)))
    # 3. 右眼轮廓
    for ang in range(0, 360, 15):
        a = math.radians(ang)
        pts.append((re[0] + eye_rx * math.cos(a), re[1] + eye_ry * math.sin(a)))
    # 瞳孔中心点
    pts.append((le[0], le[1]))
    pts.append((re[0], re[1]))

    # 4. 眉毛（眼睛上方弧线）
    brow_offset = eye_dist * 0.22
    brow_rx = eye_dist * 0.22
    for t in range(-5, 6):
        x = face_cx + (le[0] - re[0]) * 0.5 * t / 5  # 沿眼连线方向
        # 简化：在每只眼上方画弧
    for eye in (le, re):
        for t in range(-4, 5):
            x = eye[0] + t * eye_dist * 0.05
            y = eye[1] - brow_offset + abs(t) * eye_dist * 0.015
            pts.append((x, y))

    # 5. 鼻梁（眉心→鼻尖竖线点阵）
    brow_center = ((le[0] + re[0]) / 2, (le[1] + re[1]) / 2 - eye_dist * 0.05)
    for t in range(0, 11):
        r = t / 10
        x = brow_center[0] * (1 - r) + nose[0] * r
        y = brow_center[1] * (1 - r) + nose[1] * r
        pts.append((x, y))
    # 鼻翼（鼻尖两侧小点阵）
    for ang in range(-60, 61, 20):
        a = math.radians(ang + 90)
        nw = eye_dist * 0.10
        pts.append((nose[0] + nw * math.cos(a), nose[1] + nw * math.sin(a)))

    # 6. 嘴唇（横向椭圆点阵）
    mouth_rx = abs(lm_[0] - rm[0]) / 2 + eye_dist * 0.04
    mouth_ry = eye_dist * 0.06
    for ang in range(0, 360, 12):
        a = math.radians(ang)
        pts.append((mouth_cx + mouth_rx * math.cos(a), mouth_cy + mouth_ry * math.sin(a)))
    # 嘴唇中线
    for t in range(-5, 6):
        x = mouth_cx + t * mouth_rx * 0.18
        y = mouth_cy
        pts.append((x, y))

    return pts


# ---------- 激光点绘制 ----------

def _draw_laser_dot(frame, x: float, y: float, color=COLOR_LASER,
                    core_r: int = 1, glow_r: int = 5, glow_alpha: float = 0.35) -> None:
    """绘制单个激光点：中心亮白 + 外圈蓝色光晕。"""
    xi, yi = int(x), int(y)
    H, W = frame.shape[:2]
    if xi < -glow_r or yi < -glow_r or xi >= W + glow_r or yi >= H + glow_r:
        return
    # 外圈光晕（alpha 叠加）
    if glow_r > 0:
        overlay = frame.copy()
        cv2.circle(overlay, (xi, yi), glow_r, color, -1, cv2.LINE_AA)
        cv2.addWeighted(overlay, glow_alpha, frame, 1 - glow_alpha, 0, frame)
    # 中心核心
    cv2.circle(frame, (xi, yi), core_r, COLOR_LASER_CORE, -1, cv2.LINE_AA)


def _draw_laser_mesh(frame, face, color=COLOR_LASER, t: float | None = None) -> None:
    """绘制蓝色激光点阵（面部轮廓 + 五官）。"""
    pts = _face_mesh_points(face)
    # 微动：点阵随时间轻微脉动，模拟激光扫描的呼吸感
    t = t if t is not None else time.time()
    pulse = 0.85 + 0.15 * (math.sin(t * 3) * 0.5 + 0.5)
    for (x, y) in pts:
        _draw_laser_dot(frame, x, y, color, core_r=1, glow_r=5,
                        glow_alpha=0.30 * pulse)


# ---------- 简洁 UI 组件 ----------

def _draw_scan_line(frame, face, t: float) -> None:
    """简洁扫描线：单条蓝色横线，上下移动。"""
    progress = (math.sin(t * 1.6) + 1) / 2
    ly = int(face.y + progress * face.h)
    cv2.line(frame, (face.x, ly), (face.x + face.w, ly),
             COLOR_LASER, 1, cv2.LINE_AA)
    # 微光带
    overlay = frame.copy()
    cv2.line(overlay, (face.x, ly), (face.x + face.w, ly),
             COLOR_LASER, 3, cv2.LINE_AA)
    cv2.addWeighted(overlay, 0.2, frame, 0.8, 0, frame)


def _draw_face_box(frame, face, color, t: float) -> None:
    """简洁人脸框：细线圆角矩形 + 四角标记。"""
    x, y, w, h = face.x, face.y, face.w, face.h
    # 细线矩形
    cv2.rectangle(frame, (x, y), (x + w, y + h), color, 1, cv2.LINE_AA)
    # 四角加粗标记
    cl = max(12, min(w, h) // 6)
    for (cx, cy, dx, dy) in [
        (x, y, cl, 0), (x, y, 0, cl),           # 左上
        (x + w, y, -cl, 0), (x + w, y, 0, cl),  # 右上
        (x, y + h, cl, 0), (x, y + h, 0, -cl),  # 左下
        (x + w, y + h, -cl, 0), (x + w, y + h, 0, -cl),  # 右下
    ]:
        cv2.line(frame, (cx, cy), (cx + dx, cy + dy), color, 2, cv2.LINE_AA)


def _draw_label(frame, face, label: str, color, confidence: float | None) -> None:
    """简洁标签胶囊：人脸框上方。"""
    text = label
    if confidence is not None:
        text += f"  {confidence:.2f}"
    (tw, th), _ = cv2.getTextSize(text, cv2.FONT_HERSHEY_SIMPLEX, 0.5, 1)
    pad_x, pad_y = 8, 5
    bw, bh = tw + pad_x * 2, th + pad_y * 2
    bx = face.x
    by = max(0, face.y - bh - 4)
    # 半透明黑底
    overlay = frame.copy()
    cv2.rectangle(overlay, (bx, by), (bx + bw, by + bh), COLOR_BG_BAR, -1, cv2.LINE_AA)
    cv2.addWeighted(overlay, 0.65, frame, 0.35, 0, frame)
    # 左侧色条
    cv2.rectangle(frame, (bx, by), (bx + 3, by + bh), color, -1, cv2.LINE_AA)
    # 文字
    cv2.putText(frame, text, (bx + pad_x, by + pad_y + th - 1),
                cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 1, cv2.LINE_AA)


def _draw_top_bar(frame, status_text: str, color) -> None:
    """顶部简洁状态条：左上角小圆点 + 标题。"""
    cv2.putText(frame, "FaceGuard", (14, 22),
                cv2.FONT_HERSHEY_SIMPLEX, 0.55, COLOR_TEXT, 1, cv2.LINE_AA)
    cv2.circle(frame, (8, 18), 3, color, -1, cv2.LINE_AA)
    cv2.putText(frame, status_text, (100, 22),
                cv2.FONT_HERSHEY_SIMPLEX, 0.45, COLOR_TEXT_DIM, 1, cv2.LINE_AA)


def _draw_status_bar(frame, status: str, color) -> None:
    """底部简洁状态栏。"""
    h, w = frame.shape[:2]
    bar_h = 30
    # 半透明黑底
    overlay = frame.copy()
    cv2.rectangle(overlay, (0, h - bar_h), (w, h), COLOR_BG_BAR, -1)
    cv2.addWeighted(overlay, 0.7, frame, 0.3, 0, frame)
    # 状态点
    cv2.circle(frame, (16, h - bar_h // 2), 3, color, -1, cv2.LINE_AA)
    cv2.putText(frame, status, (28, h - 11),
                cv2.FONT_HERSHEY_SIMPLEX, 0.5, COLOR_TEXT, 1, cv2.LINE_AA)


# ---------- 主渲染入口 ----------

def render_overlay(frame, faces, owner_name, confidence, status: str,
                   cfg: dict, t: float | None = None) -> np.ndarray:
    """简洁风格主渲染：蓝色激光点阵 + 细线人脸框 + 状态栏。"""
    t = t if t is not None else time.time()
    ocfg = cfg.get("overlay", {})
    show_scan = ocfg.get("show_scanline", True)
    show_conf = ocfg.get("show_confidence", True)

    top_color = COLOR_OWNER  # 默认蓝
    for face in faces:
        is_owner = owner_name is not None
        color = COLOR_OWNER if is_owner else COLOR_STRANGER
        label = owner_name if is_owner else "Unknown"

        # 蓝色激光点阵（核心可视化，跟随 landmarks 实时变动）
        _draw_laser_mesh(frame, face, color, t)

        # 简洁人脸框
        _draw_face_box(frame, face, color, t)

        # 扫描线（识别中时显示）
        if show_scan and not is_owner:
            _draw_scan_line(frame, face, t)

        # 标签
        _draw_label(frame, face, label, color,
                    confidence if show_conf else None)

    # 顶部 + 底部状态栏
    top_status = "Active" if faces else "Standby"
    _draw_top_bar(frame, top_status, top_color)
    _draw_status_bar(frame, status, top_color)
    return frame
