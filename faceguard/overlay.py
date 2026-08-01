"""液态玻璃（Liquid Glass）风格识别画面可视化。

苹果 Liquid Glass 视觉要素：
  - 毛玻璃模糊背景层
  - 流光渐变边框（动态色相旋转）
  - 圆角玻璃面板
  - 折射高光（顶部亮、底部暗）
  - 呼吸光晕
  - 扫描线带柔光
全部用 OpenCV 绘制，无外部资源。
"""

from __future__ import annotations

import math
import time

import cv2
import numpy as np


# ---------- 液态玻璃配色（BGR，模拟苹果系统色）----------
COLOR_OWNER = (120, 230, 180)       # 本人 - 液态薄荷绿
COLOR_STRANGER = (110, 110, 255)    # 陌生人 - 液态红
COLOR_INTRUDER = (90, 180, 255)     # 入侵 - 液态橙
COLOR_GLASS_EDGE = (255, 255, 255)  # 玻璃边 - 白
COLOR_HIGHLIGHT = (255, 255, 255)   # 高光
COLOR_TEXT = (255, 255, 255)
COLOR_TEXT_SHADOW = (0, 0, 0)


# ---------- 工具 ----------

def _rounded_rect_mask(size: tuple[int, int], radius: int) -> np.ndarray:
    """生成圆角矩形 mask（白=有效，黑=透明）。"""
    w, h = size
    mask = np.zeros((h, w), dtype=np.uint8)
    cv2.rectangle(mask, (radius, 0), (w - radius, h), 255, -1)
    cv2.rectangle(mask, (0, radius), (w, h - radius), 255, -1)
    cv2.circle(mask, (radius, radius), radius, 255, -1)
    cv2.circle(mask, (w - radius, radius), radius, 255, -1)
    cv2.circle(mask, (radius, h - radius), radius, 255, -1)
    cv2.circle(mask, (w - radius, h - radius), radius, 255, -1)
    return mask


def _blend_glass(frame: np.ndarray, roi: np.ndarray, alpha: float = 0.55) -> np.ndarray:
    """对 ROI 区域做毛玻璃效果：高斯模糊 + 半透明白色叠加。"""
    blurred = cv2.GaussianBlur(roi, (21, 21), 0)
    glass = cv2.addWeighted(roi, 1 - alpha, blurred, alpha, 0)
    # 轻微提亮，模拟玻璃折射
    glass = cv2.add(glass, np.full_like(glass, 8))
    return glass


def _hue_rotate(base: tuple[int, int, int], t: float) -> tuple[int, int, int]:
    """随时间在 base 附近做色相微动，模拟流光。"""
    import colorsys
    b, g, r = [x / 255.0 for x in base]
    h, s, v = colorsys.rgb_to_hsv(r, g, b)
    h = (h + 0.05 * math.sin(t * 0.8)) % 1.0
    r2, g2, b2 = colorsys.hsv_to_rgb(h, s, v)
    return (int(b2 * 255), int(g2 * 255), int(r2 * 255))


# ---------- 玻璃面板 ----------

def draw_glass_panel(frame, x: int, y: int, w: int, h: int,
                     color=COLOR_GLASS_EDGE, t: float | None = None) -> None:
    """绘制一块液态玻璃面板（毛玻璃底 + 圆角 + 流光边 + 高光）。"""
    t = t if t is not None else time.time()
    H, W = frame.shape[:2]
    x1, y1 = max(0, x), max(0, y)
    x2, y2 = min(W, x + w), min(H, y + h)
    w2, h2 = x2 - x1, y2 - y1
    if w2 <= 4 or h2 <= 4:
        return

    radius = min(18, w2 // 6, h2 // 6)
    # 1. 毛玻璃底
    roi = frame[y1:y2, x1:x2]
    glass = _blend_glass(frame, roi, alpha=0.6)
    # 2. 圆角 mask 应用
    mask = _rounded_rect_mask((w2, h2), radius)
    mask_3 = cv2.merge([mask, mask, mask])
    blended = cv2.bitwise_and(glass, mask_3)
    inv = cv2.bitwise_and(roi, cv2.bitwise_not(mask_3))
    frame[y1:y2, x1:x2] = cv2.add(blended, inv)

    # 3. 折射高光：顶部 1/3 加白色渐变
    hl_h = max(2, h2 // 3)
    hl = np.zeros((hl_h, w2, 3), dtype=np.uint8)
    for i in range(hl_h):
        a = int(40 * (1 - i / hl_h))  # 顶部最亮
        hl[i, :] = [a, a, a]
    hl_mask = _rounded_rect_mask((w2, hl_h + radius), radius)[:hl_h]
    hl_mask_3 = cv2.merge([hl_mask, hl_mask, hl_mask])
    hl_roi = frame[y1:y1 + hl_h, x1:x2]
    frame[y1:y1 + hl_h, x1:x2] = cv2.add(hl_roi, cv2.bitwise_and(hl, hl_mask_3))

    # 4. 流光边框（圆角描边 + 色相微动）
    edge_color = _hue_rotate(color, t)
    overlay = frame.copy()
    cv2.rectangle(overlay, (x1, y1), (x2, y2), edge_color, 1, cv2.LINE_AA)
    # 用 mask 做圆角描边
    edge_mask = np.zeros((h2, w2), dtype=np.uint8)
    cv2.rectangle(edge_mask, (0, 0), (w2, h2), 255, 1)
    inner = _rounded_rect_mask((w2, h2), radius)
    edge_only = cv2.subtract(edge_mask, cv2.erode(inner, np.ones((3, 3), np.uint8)))
    edge_color_layer = np.full((h2, w2, 3), edge_color, dtype=np.uint8)
    edge_3 = cv2.bitwise_and(edge_color_layer, cv2.merge([edge_only, edge_only, edge_only]))
    # 把边框画到 overlay 再混合（柔光感）
    roi2 = frame[y1:y2, x1:x2]
    frame[y1:y2, x1:x2] = cv2.add(roi2, edge_3)


# ---------- 人脸框（液态玻璃风格）----------

def draw_face_glass(frame, face, label: str, color, confidence: float | None = None,
                    show_conf: bool = True, t: float | None = None) -> None:
    """液态玻璃风格人脸框：圆角玻璃面板 + 流光边 + 标签胶囊。"""
    t = t if t is not None else time.time()
    x, y, w, h = face.x, face.y, face.w, face.h
    # 主体玻璃面板
    draw_glass_panel(frame, x, y, w, h, color, t)

    # 标签胶囊（人脸框上方）
    text = label
    if show_conf and confidence is not None:
        text += f"  {confidence:.2f}"
    (tw, th), _ = cv2.getTextSize(text, cv2.FONT_HERSHEY_SIMPLEX, 0.5, 1)
    pad_x, pad_y = 10, 6
    cap_w, cap_h = tw + pad_x * 2, th + pad_y * 2
    cap_x = x
    cap_y = max(0, y - cap_h - 4)
    # 胶囊也是玻璃面板
    draw_glass_panel(frame, cap_x, cap_y, cap_w, cap_h, color, t)
    # 文字 + 阴影
    cv2.putText(frame, text, (cap_x + pad_x, cap_y + pad_y + th - 1),
                cv2.FONT_HERSHEY_SIMPLEX, 0.5, COLOR_TEXT_SHADOW, 2, cv2.LINE_AA)
    cv2.putText(frame, text, (cap_x + pad_x, cap_y + pad_y + th - 1),
                cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 1, cv2.LINE_AA)


def draw_landmarks_glass(frame, face, color, t: float | None = None) -> None:
    """液态关键点：发光圆点 + 连线。"""
    t = t if t is not None else time.time()
    glow_color = _hue_rotate(color, t)
    pts = list(face.landmarks.values())
    pairs = [("right_eye", "left_eye"), ("left_eye", "nose"),
             ("nose", "right_mouth"), ("nose", "left_mouth"),
             ("right_mouth", "left_mouth")]
    for a, b in pairs:
        cv2.line(frame, face.landmarks[a], face.landmarks[b], glow_color, 1, cv2.LINE_AA)
    for p in pts:
        # 发光：先画大半透明圆，再画小实心圆
        overlay = frame.copy()
        cv2.circle(overlay, p, 6, glow_color, -1, cv2.LINE_AA)
        cv2.addWeighted(overlay, 0.25, frame, 0.75, 0, frame)
        cv2.circle(frame, p, 3, COLOR_HIGHLIGHT, -1, cv2.LINE_AA)


def draw_scanline_glass(frame, face, t: float | None = None) -> None:
    """液态扫描线：柔光带 + 流动高光。"""
    t = t if t is not None else time.time()
    x, y, w, h = face.x, face.y, face.w, face.h
    progress = (math.sin(t * 1.8) + 1) / 2
    ly = int(y + progress * h)
    # 主扫描线
    cv2.line(frame, (x, ly), (x + w, ly), (255, 255, 255), 1, cv2.LINE_AA)
    # 柔光带（上下各 10px 渐变）
    for d in range(1, 14):
        a = max(0, 70 - d * 5)
        line_y_up = max(y, ly - d)
        line_y_dn = min(y + h, ly + d)
        if line_y_up < y + h:
            cv2.line(frame, (x, line_y_up), (x + w, line_y_up),
                     (200, 230, 255), 1, cv2.LINE_AA)
        if line_y_dn < y + h:
            cv2.line(frame, (x, line_y_dn), (x + w, line_y_dn),
                     (200, 230, 255), 1, cv2.LINE_AA)


def draw_glow_glass(frame, face, color, t: float | None = None) -> None:
    """呼吸光晕：人脸框外圈脉动发光。"""
    t = t if t is not None else time.time()
    x, y, w, h = face.x, face.y, face.w, face.h
    pulse = (math.sin(t * 2.5) + 1) / 2
    alpha = 0.10 + 0.18 * pulse
    pad = 8
    overlay = frame.copy()
    glow_color = _hue_rotate(color, t)
    cv2.rectangle(overlay, (x - pad, y - pad), (x + w + pad, y + h + pad),
                  glow_color, -1)
    cv2.addWeighted(overlay, alpha, frame, 1 - alpha, 0, frame)


def draw_status_bar_glass(frame, text: str, color=COLOR_TEXT, t: float | None = None) -> None:
    """底部状态栏（液态玻璃条）。"""
    t = t if t is not None else time.time()
    h, w = frame.shape[:2]
    bar_h = 36
    draw_glass_panel(frame, 0, h - bar_h, w, bar_h, COLOR_GLASS_EDGE, t)
    cv2.putText(frame, text, (14, h - 12), cv2.FONT_HERSHEY_SIMPLEX,
                0.55, COLOR_TEXT_SHADOW, 2, cv2.LINE_AA)
    cv2.putText(frame, text, (14, h - 12), cv2.FONT_HERSHEY_SIMPLEX,
                0.55, color, 1, cv2.LINE_AA)


def draw_title_glass(frame, title: str = "FaceGuard", t: float | None = None) -> None:
    """左上角液态玻璃标题胶囊。"""
    t = t if t is not None else time.time()
    (tw, th), _ = cv2.getTextSize(title, cv2.FONT_HERSHEY_SIMPLEX, 0.6, 1)
    pad_x, pad_y = 14, 8
    w = tw + pad_x * 2
    h = th + pad_y * 2
    draw_glass_panel(frame, 10, 10, w, h, COLOR_OWNER, t)
    cv2.putText(frame, title, (10 + pad_x, 10 + pad_y + th - 2),
                cv2.FONT_HERSHEY_SIMPLEX, 0.6, COLOR_TEXT_SHADOW, 2, cv2.LINE_AA)
    cv2.putText(frame, title, (10 + pad_x, 10 + pad_y + th - 2),
                cv2.FONT_HERSHEY_SIMPLEX, 0.6, COLOR_HIGHLIGHT, 1, cv2.LINE_AA)


# ---------- 主渲染入口 ----------

def render_overlay(frame, faces, owner_name, confidence, status: str,
                   cfg: dict, t: float | None = None) -> np.ndarray:
    """液态玻璃主渲染：在帧上叠加全部特效。"""
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
            draw_scanline_glass(frame, face, t)
        draw_glow_glass(frame, face, color, t)
        if show_lm:
            draw_landmarks_glass(frame, face, color, t)
        draw_face_glass(frame, face, label, color,
                        confidence if show_conf else None, show_conf, t)

    draw_title_glass(frame, "FaceGuard", t)
    draw_status_bar_glass(frame, status, COLOR_TEXT, t)
    return frame
