#!/usr/bin/env python3
"""
FaceGuard · 简洁风格 UI 截图生成器（蓝色激光点阵版）

设计：
  · 极简：深色背景 + 细线 + 简洁文字，无花哨玻璃/光晕/粒子
  · 蓝色激光点阵：SVG 模拟 OpenCV 渲染的激光点阵效果
    - 中心亮白点 + 外圈蓝色光晕（feGaussianBlur）
    - 面部轮廓椭圆点阵 + 五官点阵（眼睛/鼻梁/嘴唇/眉毛）
  · 实时跟随：点阵基于 landmarks 位置生成
渲染：SVG + cairosvg @ 2x 高清
"""

from __future__ import annotations

import math
from pathlib import Path

import cairosvg

OUT = Path(__file__).parent / "screenshots"
OUT.mkdir(exist_ok=True)

# 简洁配色
C_LASER = "#008CFF"      # 激光蓝
C_LASER_LT = "#4DA8FF"   # 激光蓝亮
C_LASER_DIM = "#0066CC"  # 激光蓝暗
C_RED = "#FF3B30"        # 陌生人红
C_RED_LT = "#FF6B6B"
C_AMBER = "#FF9500"      # 警告
C_WHITE = "#F5F5F7"
C_TEXT_DIM = "#8E8E93"
C_TEXT_HINT = "#48484A"
C_BG = "#0A0A0E"         # 深黑背景
C_BG_PANEL = "#1C1C1E"   # 面板底

SVG_DEFS = """
<defs>
  <!-- 激光点光晕 -->
  <filter id="laserGlow" x="-100%" y="-100%" width="300%" height="300%">
    <feGaussianBlur in="SourceGraphic" stdDeviation="2.5" result="blur"/>
    <feMerge>
      <feMergeNode in="blur"/>
      <feMergeNode in="blur"/>
      <feMergeNode in="SourceGraphic"/>
    </feMerge>
  </filter>
  <filter id="laserGlowSm" x="-100%" y="-100%" width="300%" height="300%">
    <feGaussianBlur in="SourceGraphic" stdDeviation="1.5" result="blur"/>
    <feMerge>
      <feMergeNode in="blur"/>
      <feMergeNode in="SourceGraphic"/>
    </feMerge>
  </filter>
  <!-- 扫描线光晕 -->
  <filter id="scanGlow" x="-20%" y="-200%" width="140%" height="500%">
    <feGaussianBlur in="SourceGraphic" stdDeviation="3"/>
  </filter>
  <!-- 背景渐变 -->
  <radialGradient id="bgGrad" cx="50%" cy="40%" r="70%">
    <stop offset="0%"  stop-color="#1A1A24"/>
    <stop offset="100%" stop-color="#0A0A0E"/>
  </radialGradient>
</defs>
"""


def make_bg(w: int, h: int) -> str:
    return f'<rect width="{w}" height="{h}" fill="url(#bgGrad)"/>'


def laser_dot(x: float, y: float, color: str = C_LASER, r: float = 1.5) -> str:
    """单个激光点：外圈光晕 + 中心白核。"""
    return f'''<circle cx="{x}" cy="{y}" r="{r*3}" fill="{color}" opacity="0.3" filter="url(#laserGlow)"/>
<circle cx="{x}" cy="{y}" r="{r}" fill="#ffffff" filter="url(#laserGlowSm)"/>'''


def face_mesh_dots(cx: float, cy: float, scale: float = 1,
                   color: str = C_LASER, w: float = 200, h: float = 220) -> str:
    """生成面部轮廓 + 五官的激光点阵（模拟 OpenCV 实时渲染）。

    基于 5 landmarks 位置插值生成密集点阵，模拟实时跟随效果。
    """
    dots = []
    # 5 landmarks 基准位置（相对人脸中心）
    le = (cx - 35*scale, cy - 15*scale)   # 左眼
    re = (cx + 35*scale, cy - 15*scale)   # 右眼
    nose = (cx, cy + 15*scale)            # 鼻
    rm = (cx - 25*scale, cy + 45*scale)   # 右嘴角
    lm_ = (cx + 25*scale, cy + 45*scale)  # 左嘴角
    eye_dist = 70 * scale

    # 1. 面部外轮廓（椭圆点阵）
    rx, ry = w*0.42, h*0.48
    for ang in range(0, 360, 6):
        a = math.radians(ang)
        px = cx + rx * math.cos(a)
        py = cy + ry * math.sin(a) + h*0.02
        dots.append(laser_dot(px, py, color, 1.2))

    # 2. 左眼轮廓（椭圆点阵）
    erx, ery = eye_dist*0.18, eye_dist*0.12
    for ang in range(0, 360, 15):
        a = math.radians(ang)
        dots.append(laser_dot(le[0]+erx*math.cos(a), le[1]+ery*math.sin(a), color, 1.5))
    # 3. 右眼轮廓
    for ang in range(0, 360, 15):
        a = math.radians(ang)
        dots.append(laser_dot(re[0]+erx*math.cos(a), re[1]+ery*math.sin(a), color, 1.5))
    # 瞳孔
    dots.append(laser_dot(le[0], le[1], color, 2))
    dots.append(laser_dot(re[0], re[1], color, 2))

    # 4. 眉毛（弧线点阵）
    brow_off = eye_dist * 0.22
    for eye in (le, re):
        for t in range(-4, 5):
            x = eye[0] + t * eye_dist * 0.05
            y = eye[1] - brow_off + abs(t) * eye_dist * 0.015
            dots.append(laser_dot(x, y, color, 1.3))

    # 5. 鼻梁（竖线点阵）
    brow_c = ((le[0]+re[0])/2, (le[1]+re[1])/2 - eye_dist*0.05)
    for t in range(0, 11):
        r = t / 10
        x = brow_c[0]*(1-r) + nose[0]*r
        y = brow_c[1]*(1-r) + nose[1]*r
        dots.append(laser_dot(x, y, color, 1.2))
    # 鼻翼
    for ang in range(-60, 61, 20):
        a = math.radians(ang + 90)
        nw = eye_dist * 0.10
        dots.append(laser_dot(nose[0]+nw*math.cos(a), nose[1]+nw*math.sin(a), color, 1.2))

    # 6. 嘴唇（椭圆点阵）
    mouth_cx = (rm[0]+lm_[0])/2
    mouth_cy = (rm[1]+lm_[1])/2
    mrx = abs(lm_[0]-rm[0])/2 + eye_dist*0.04
    mry = eye_dist * 0.06
    for ang in range(0, 360, 12):
        a = math.radians(ang)
        dots.append(laser_dot(mouth_cx+mrx*math.cos(a), mouth_cy+mry*math.sin(a), color, 1.3))
    # 嘴唇中线
    for t in range(-5, 6):
        dots.append(laser_dot(mouth_cx+t*mrx*0.18, mouth_cy, color, 1.2))

    return "\n".join(dots)


def face_box(x: float, y: float, w: float, h: float, color: str) -> str:
    """简洁人脸框：细线矩形 + 四角标记。"""
    cl = max(12, min(w, h) / 6)
    parts = [f'<rect x="{x}" y="{y}" width="{w}" height="{h}" fill="none" stroke="{color}" stroke-width="1" opacity="0.7"/>']
    # 四角
    corners = [
        (x, y, cl, 0), (x, y, 0, cl),
        (x+w, y, -cl, 0), (x+w, y, 0, cl),
        (x, y+h, cl, 0), (x, y+h, 0, -cl),
        (x+w, y+h, -cl, 0), (x+w, y+h, 0, -cl),
    ]
    for cx, cy, dx, dy in corners:
        parts.append(f'<line x1="{cx}" y1="{cy}" x2="{cx+dx}" y2="{cy+dy}" stroke="{color}" stroke-width="2.5" stroke-linecap="round"/>')
    return "\n".join(parts)


def label_pill(x: float, y: float, text: str, color: str) -> str:
    """简洁标签：半透明黑底 + 左侧色条 + 文字。"""
    w = 12 + len(text) * 7.2
    h = 22
    return f'''<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="3" fill="{C_BG}" opacity="0.75"/>
<rect x="{x}" y="{y}" width="3" height="{h}" fill="{color}"/>
<text x="{x+10}" y="{y+15}" font-family="Source Han Sans SC, sans-serif" font-size="12" font-weight="600" fill="{color}">{text}</text>'''


def top_bar(status: str, color: str) -> str:
    return f'''<circle cx="14" cy="20" r="3" fill="{color}"/>
<text x="24" y="25" font-family="Source Han Sans SC, sans-serif" font-size="13" font-weight="600" fill="{C_WHITE}">FaceGuard</text>
<text x="100" y="25" font-family="Source Han Sans SC, sans-serif" font-size="11" fill="{C_TEXT_DIM}">{status}</text>'''


def status_bar(w: int, h: int, status: str, color: str) -> str:
    bar_h = 30
    y = h - bar_h
    return f'''<rect x="0" y="{y}" width="{w}" height="{bar_h}" fill="{C_BG}" opacity="0.8"/>
<circle cx="16" cy="{y+bar_h//2}" r="3" fill="{color}"/>
<text x="28" y="{y+bar_h//2+5}" font-family="Source Han Sans SC, sans-serif" font-size="12" font-weight="500" fill="{C_WHITE}">{status}</text>'''


def render_svg(content: str, filename: str, w: int, h: int) -> bool:
    svg = f'''<?xml version="1.0" encoding="UTF-8"?>
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {w} {h}" width="{w}" height="{h}">
{SVG_DEFS}
{make_bg(w, h)}
{content}
</svg>'''
    svg_path = OUT / f"{filename}.svg"
    svg_path.write_text(svg, encoding="utf-8")
    png_path = OUT / f"{filename}.png"
    try:
        cairosvg.svg2png(bytestring=svg.encode("utf-8"),
                         write_to=str(png_path),
                         output_width=w*2, output_height=h*2)
        return True
    except Exception as e:
        print(f"  渲染失败 {filename}: {e}")
        return False


def scan_line(x, y, w, h, color, pos=0.4):
    ly = y + h * pos
    return f'''<rect x="{x}" y="{ly-6}" width="{w}" height="12" fill="{color}" opacity="0.15" filter="url(#scanGlow)"/>
<rect x="{x}" y="{ly-0.5}" width="{w}" height="1" fill="{color}"/>'''


# ═══════════════════════════════════════════════════════════════
#  8 个界面
# ═══════════════════════════════════════════════════════════════

def shot_01_owner():
    W, H = 800, 600
    cx, cy = 400, 290
    fw, fh = 220, 240
    content = f'''
  <!-- 人脸剪影（暗色，让点阵更突出） -->
  <ellipse cx="{cx}" cy="{cy-30}" rx="55" ry="70" fill="#1A1A24" opacity="0.8"/>
  <path d="M{cx-75},{cy+80} Q{cx-75},{cy+20} {cx},{cy+20} Q{cx+75},{cy+20} {cx+75},{cy+80} Z" fill="#1A1A24" opacity="0.8"/>

  <!-- 蓝色激光点阵（核心可视化） -->
  {face_mesh_dots(cx, cy, 1.0, C_LASER, fw, fh)}

  <!-- 简洁人脸框 -->
  {face_box(cx-fw//2, cy-fh//2-10, fw, fh, C_LASER)}

  <!-- 标签 -->
  {label_pill(cx-fw//2, cy-fh//2-36, "Owner  0.99", C_LASER)}

  <!-- 顶部状态 -->
  {top_bar("Active · 已识别", C_LASER)}

  <!-- 底部状态栏 -->
  {status_bar(W, H, "✓ 识别成功 · 已解锁", C_LASER)}'''
    return render_svg(content, "01_recognize_owner", W, H)


def shot_02_stranger():
    W, H = 800, 600
    cx, cy = 400, 290
    fw, fh = 220, 240
    content = f'''
  <ellipse cx="{cx}" cy="{cy-30}" rx="55" ry="70" fill="#241A1A" opacity="0.8"/>
  <path d="M{cx-75},{cy+80} Q{cx-75},{cy+20} {cx},{cy+20} Q{cx+75},{cy+20} {cx+75},{cy+80} Z" fill="#241A1A" opacity="0.8"/>

  <!-- 红色激光点阵（陌生人） -->
  {face_mesh_dots(cx, cy, 1.0, C_RED, fw, fh)}

  {face_box(cx-fw//2, cy-fh//2-10, fw, fh, C_RED)}
  {label_pill(cx-fw//2, cy-fh//2-36, "Unknown  0.12", C_RED)}

  <!-- 扫描线 -->
  {scan_line(cx-fw//2, cy-fh//2-10, fw, fh, C_RED, 0.45)}

  {top_bar("Alert · 陌生人", C_RED)}
  {status_bar(W, H, "✕ 识别失败 · 已抓拍并告警", C_RED)}'''
    return render_svg(content, "02_recognize_stranger", W, H)


def shot_03_guardian():
    W, H = 800, 600
    content = f'''
  <!-- 本人（左，蓝） -->
  <ellipse cx="250" cy="260" rx="42" ry="55" fill="#1A1A24" opacity="0.8"/>
  <path d="M195,340 Q195,290 250,290 Q305,290 305,340 Z" fill="#1A1A24" opacity="0.8"/>
  {face_mesh_dots(250, 290, 0.85, C_LASER, 170, 180)}
  {face_box(165, 200, 170, 180, C_LASER)}
  {label_pill(165, 178, "Owner", C_LASER)}

  <!-- 入侵者（右，红） -->
  <ellipse cx="560" cy="240" rx="45" ry="58" fill="#241A1A" opacity="0.8"/>
  <path d="M500,325 Q500,275 560,275 Q620,275 620,325 Z" fill="#241A1A" opacity="0.8"/>
  {face_mesh_dots(560, 270, 0.9, C_RED, 180, 190)}
  {face_box(470, 175, 180, 190, C_RED)}
  {label_pill(470, 153, "Intruder", C_RED)}

  <!-- 检测连线 -->
  <line x1="335" y1="290" x2="470" y2="270" stroke="{C_AMBER}" stroke-width="1" stroke-dasharray="5 3" opacity="0.6"/>
  <text x="402" y="270" font-family="Source Han Sans SC, sans-serif" font-size="11" font-weight="600" fill="{C_AMBER}" text-anchor="middle">behind</text>

  {top_bar("Alert · 身后入侵", C_AMBER)}
  {status_bar(W, H, "⚠ 守护模式 · 检测到身后他人", C_AMBER)}'''
    return render_svg(content, "03_guardian_intruder", W, H)


def shot_04_absence():
    W, H = 800, 600
    cx, cy = 400, 290
    content = f'''
  <!-- 大数字倒计时 -->
  <text x="{cx}" y="{cy-20}" font-family="Source Han Sans SC, sans-serif" font-size="88" font-weight="200" fill="{C_LASER_LT}" text-anchor="middle">5:00</text>
  <text x="{cx}" y="{cy+20}" font-family="Source Han Sans SC, sans-serif" font-size="16" font-weight="400" fill="{C_TEXT_DIM}" text-anchor="middle">后进入休眠</text>

  <!-- 进度环 -->
  <circle cx="{cx}" cy="{cy+90}" r="42" fill="none" stroke="#ffffff" stroke-opacity="0.1" stroke-width="6"/>
  <circle cx="{cx}" cy="{cy+90}" r="42" fill="none" stroke="{C_LASER}" stroke-width="6" stroke-linecap="round"
          stroke-dasharray="264" stroke-dashoffset="80" transform="rotate(-90 {cx} {cy+90})" filter="url(#laserGlow)"/>

  {top_bar("Away · 离开模式", C_LASER)}
  {status_bar(W, H, "用户已离开 · 已锁屏 · 5 分钟后休眠", C_LASER)}'''
    return render_svg(content, "04_absence", W, H)


def shot_05_recognizing():
    W, H = 800, 600
    cx, cy = 270, 290
    fw, fh = 220, 240
    content = f'''
  <ellipse cx="{cx}" cy="{cy-30}" rx="55" ry="70" fill="#1A1A24" opacity="0.8"/>
  <path d="M{cx-75},{cy+80} Q{cx-75},{cy+20} {cx},{cy+20} Q{cx+75},{cy+20} {cx+75},{cy+80} Z" fill="#1A1A24" opacity="0.8"/>

  <!-- 蓝色激光点阵 -->
  {face_mesh_dots(cx, cy, 1.0, C_LASER_LT, fw, fh)}

  <!-- 虚线人脸框（扫描中） -->
  <rect x="{cx-fw//2}" y="{cy-fh//2-10}" width="{fw}" height="{fh}" fill="none" stroke="{C_LASER_LT}" stroke-width="1" stroke-dasharray="8 5" opacity="0.7"/>

  <!-- 扫描线 -->
  {scan_line(cx-fw//2, cy-fh//2-10, fw, fh, C_LASER_LT, 0.4)}

  <!-- 右侧进度面板（简洁） -->
  <text x="500" y="180" font-family="Source Han Sans SC, sans-serif" font-size="16" font-weight="600" fill="{C_WHITE}">正在识别</text>
  <text x="500" y="205" font-family="Source Han Sans SC, sans-serif" font-size="11" fill="{C_TEXT_DIM}">多帧确认确保安全</text>

  <text x="500" y="245" font-family="Source Han Sans SC, sans-serif" font-size="12" fill="{C_TEXT_DIM}">多帧确认</text>
  <rect x="500" y="253" width="240" height="6" rx="3" fill="#ffffff" opacity="0.1"/>
  <rect x="500" y="253" width="161" height="6" rx="3" fill="{C_LASER_LT}" filter="url(#laserGlow)"/>
  <text x="740" y="245" font-family="Source Han Sans SC, sans-serif" font-size="12" font-weight="600" fill="{C_LASER_LT}" text-anchor="end">2/3</text>

  <text x="500" y="290" font-family="Source Han Sans SC, sans-serif" font-size="12" fill="{C_TEXT_DIM}">特征提取</text>
  <rect x="500" y="298" width="240" height="6" rx="3" fill="#ffffff" opacity="0.1"/>
  <rect x="500" y="298" width="204" height="6" rx="3" fill="{C_LASER_LT}" filter="url(#laserGlow)"/>
  <text x="740" y="290" font-family="Source Han Sans SC, sans-serif" font-size="12" font-weight="600" fill="{C_LASER_LT}" text-anchor="end">85%</text>

  <text x="500" y="335" font-family="Source Han Sans SC, sans-serif" font-size="12" fill="{C_TEXT_DIM}">活体检测</text>
  <rect x="500" y="343" width="240" height="6" rx="3" fill="#ffffff" opacity="0.1"/>
  <rect x="500" y="343" width="221" height="6" rx="3" fill="{C_LASER_LT}" filter="url(#laserGlow)"/>
  <text x="740" y="335" font-family="Source Han Sans SC, sans-serif" font-size="12" font-weight="600" fill="{C_LASER_LT}" text-anchor="end">92%</text>

  {top_bar("Scanning · 识别中", C_LASER_LT)}
  {status_bar(W, H, "◌ 识别中 · 多帧确认 2/3", C_LASER_LT)}'''
    return render_svg(content, "05_recognizing", W, H)


def shot_06_settings():
    W, H = 900, 1080
    y = 50
    parts = []
    # 标题
    parts.append(f'<text x="50" y="{y+30}" font-family="Source Han Sans SC, sans-serif" font-size="28" font-weight="700" fill="{C_WHITE}">FaceGuard</text>')
    parts.append(f'<text x="52" y="{y+55}" font-family="Source Han Sans SC, sans-serif" font-size="13" fill="{C_TEXT_DIM}">Settings · 人脸解锁守护</text>')
    parts.append(f'<text x="{W-50}" y="{y+30}" font-family="Source Han Sans SC, sans-serif" font-size="13" fill="{C_TEXT_DIM}" text-anchor="end">v2.1.2</text>')
    parts.append(f'<line x1="50" y1="{y+70}" x2="{W-50}" y2="{y+70}" stroke="#ffffff" stroke-opacity="0.08"/>')

    def section(sy, title, color, rows):
        r = [f'<circle cx="60" cy="{sy+22}" r="4" fill="{color}"/>',
             f'<text x="74" y="{sy+27}" font-family="Source Han Sans SC, sans-serif" font-size="15" font-weight="700" fill="{C_WHITE}">{title}</text>']
        for i, (label, val, hint) in enumerate(rows):
            ry = sy + 60 + i * 36
            r.append(f'<text x="60" y="{ry+12}" font-family="Source Han Sans SC, sans-serif" font-size="12" fill="{C_TEXT_DIM}">{label}</text>')
            r.append(f'<rect x="220" y="{ry}" width="140" height="26" rx="4" fill="#ffffff" fill-opacity="0.06" stroke="#ffffff" stroke-opacity="0.1"/>')
            r.append(f'<text x="230" y="{ry+17}" font-family="Source Han Sans SC, sans-serif" font-size="12" font-weight="600" fill="{C_WHITE}">{val}</text>')
            if hint:
                r.append(f'<text x="370" y="{ry+17}" font-family="Source Han Sans SC, sans-serif" font-size="10" fill="{C_TEXT_HINT}">{hint}</text>')
        return "\n".join(r)

    parts.append(section(150, "识别引擎", C_LASER, [
        ("置信度阈值", "0.55", "0.3–0.8"),
        ("确认帧数", "3", "帧"),
        ("摄像头序号", "0", ""),
        ("识别帧率", "15 fps", ""),
    ]))

    # 模型选择
    my = 330
    parts.append(f'<circle cx="60" cy="{my+22}" r="4" fill="{C_LASER_LT}"/>')
    parts.append(f'<text x="74" y="{my+27}" font-family="Source Han Sans SC, sans-serif" font-size="15" font-weight="700" fill="{C_WHITE}">识别模型</text>')
    models = [
        (60, "YuNet + SFace", "默认 · 99.5%", "38 MB", C_LASER, True),
        (320, "MobileFaceNet", "轻量 · 99.0%", "5 MB", C_TEXT_DIM, False),
        (580, "ArcFace ResNet50", "高精度 · 99.8%", "170 MB", C_TEXT_DIM, False),
    ]
    for mx, name, desc, size, color, sel in models:
        cw = 260
        cy = my + 50
        if sel:
            parts.append(f'<rect x="{mx}" y="{cy}" width="{cw}" height="80" rx="8" fill="{color}" fill-opacity="0.1" stroke="{color}" stroke-width="1.5"/>')
        else:
            parts.append(f'<rect x="{mx}" y="{cy}" width="{cw}" height="80" rx="8" fill="#ffffff" fill-opacity="0.03" stroke="#ffffff" stroke-opacity="0.08"/>')
        parts.append(f'<circle cx="{mx+18}" cy="{cy+20}" r="3" fill="{color}"/>')
        parts.append(f'<text x="{mx+28}" y="{cy+25}" font-family="Source Han Sans SC, sans-serif" font-size="13" font-weight="600" fill="{"#fff" if sel else C_WHITE}">{name}</text>')
        parts.append(f'<text x="{mx+18}" y="{cy+48}" font-family="Source Han Sans SC, sans-serif" font-size="11" fill="{C_TEXT_DIM}">{desc}</text>')
        parts.append(f'<text x="{mx+18}" y="{cy+66}" font-family="Source Han Sans SC, sans-serif" font-size="10" fill="{C_TEXT_HINT}">{size}</text>')

    parts.append(section(490, "自适应学习", C_LASER_LT, [
        ("每用户最多", "30", "个样本"),
        ("冷却秒数", "300", ""),
    ]))
    # 自适应开关
    parts.append(f'<rect x="{W-110}" y="490" width="44" height="24" rx="12" fill="{C_LASER}"/>')
    parts.append(f'<circle cx="{W-90}" cy="502" r="9" fill="#fff"/>')
    parts.append(f'<text x="60" y="540" font-family="Source Han Sans SC, sans-serif" font-size="12" fill="{C_WHITE}">成功解锁后增量学习</text>')
    parts.append(f'<text x="60" y="558" font-family="Source Han Sans SC, sans-serif" font-size="10" fill="{C_TEXT_HINT}">程序自动记住你脸部变化（光线/角度/表情）</text>')

    parts.append(section(620, "邮件告警", C_AMBER, [
        ("SMTP 服务器", "smtp.qq.com", ""),
        ("发件邮箱", "1247053973@qq.com", ""),
        ("授权码", "●●●●●●●●", ""),
        ("告警冷却", "60", "秒"),
    ]))

    parts.append(section(820, "离开锁屏休眠", C_LASER, [
        ("离开锁屏", "300", "秒"),
        ("锁屏休眠", "300", "秒"),
    ]))

    # 功能开关
    parts.append(f'<circle cx="60" cy="980" r="4" fill="{C_LASER_LT}"/>')
    parts.append(f'<text x="74" y="985" font-family="Source Han Sans SC, sans-serif" font-size="15" font-weight="700" fill="{C_WHITE}">功能开关</text>')
    parts.append(f'<text x="60" y="1020" font-family="Source Han Sans SC, sans-serif" font-size="12" fill="{C_WHITE}">身后入侵守护</text>')
    parts.append(f'<rect x="{W-110}" y="1005" width="44" height="24" rx="12" fill="{C_LASER}"/>')
    parts.append(f'<circle cx="{W-90}" cy="1017" r="9" fill="#fff"/>')
    parts.append(f'<text x="300" y="1020" font-family="Source Han Sans SC, sans-serif" font-size="12" fill="{C_WHITE}">注册表自启</text>')
    parts.append(f'<rect x="{W-370}" y="1005" width="44" height="24" rx="12" fill="{C_LASER}"/>')
    parts.append(f'<circle cx="{W-350}" cy="1017" r="9" fill="#fff"/>')

    # 保存按钮
    parts.append(f'<rect x="{W//2-100}" y="1050" width="200" height="40" rx="20" fill="{C_LASER}"/>')
    parts.append(f'<text x="{W//2}" y="1075" font-family="Source Han Sans SC, sans-serif" font-size="14" font-weight="700" fill="#0A0A0E" text-anchor="middle">保存设置</text>')

    return render_svg("\n".join(parts), "06_settings_panel", W, H)


def shot_07_enroll():
    W, H = 800, 600
    cx, cy = 400, 290
    fw, fh = 230, 250
    content = f'''
  <ellipse cx="{cx}" cy="{cy-30}" rx="58" ry="73" fill="#1A1A24" opacity="0.8"/>
  <path d="M{cx-78},{cy+82} Q{cx-78},{cy+22} {cx},{cy+22} Q{cx+78},{cy+22} {cx+78},{cy+82} Z" fill="#1A1A24" opacity="0.8"/>

  <!-- 蓝色激光点阵（注册中） -->
  {face_mesh_dots(cx, cy, 1.05, C_LASER, fw, fh)}

  <!-- 人脸框 -->
  {face_box(cx-fw//2, cy-fh//2-10, fw, fh, C_LASER)}

  <!-- 扫描线 -->
  {scan_line(cx-fw//2, cy-fh//2-10, fw, fh, C_LASER, 0.35)}

  <!-- 采集进度 -->
  <rect x="30" y="100" width="200" height="28" rx="4" fill="{C_BG}" opacity="0.75"/>
  <rect x="30" y="100" width="3" height="28" fill="{C_LASER}"/>
  <text x="44" y="118" font-family="Source Han Sans SC, sans-serif" font-size="13" font-weight="600" fill="{C_LASER}">采集 5/8</text>
  <text x="120" y="118" font-family="Source Han Sans SC, sans-serif" font-size="11" fill="{C_TEXT_DIM}">请正对摄像头</text>

  <!-- 角度引导 -->
  <rect x="250" y="100" width="280" height="28" rx="4" fill="{C_BG}" opacity="0.75"/>
  <text x="264" y="118" font-family="Source Han Sans SC, sans-serif" font-size="11" fill="{C_TEXT_DIM}">← 正面 → 左侧 → 右侧</text>
  <text x="520" y="118" font-family="Source Han Sans SC, sans-serif" font-size="11" font-weight="600" fill="{C_LASER}" text-anchor="end">当前: 正面</text>

  {top_bar("Enroll · 注册中", C_LASER)}

  <!-- 底部进度条 -->
  <rect x="60" y="{H-65}" width="{W-120}" height="6" rx="3" fill="#ffffff" opacity="0.1"/>
  <rect x="60" y="{H-65}" width="{(W-120)*0.625}" height="6" rx="3" fill="{C_LASER}" filter="url(#laserGlow)"/>
  <text x="60" y="{H-75}" font-family="Source Han Sans SC, sans-serif" font-size="11" fill="{C_TEXT_DIM}">注册进度</text>
  <text x="{W-60}" y="{H-75}" font-family="Source Han Sans SC, sans-serif" font-size="12" font-weight="600" fill="{C_LASER}" text-anchor="end">62%</text>

  {status_bar(W, H, "注册人脸 · 采集多角度特征", C_LASER)}'''
    return render_svg(content, "07_enroll", W, H)


def shot_08_dashboard():
    W, H = 800, 600
    parts = []
    # 主面板
    parts.append(f'<rect x="80" y="60" width="{W-160}" height="{H-120}" rx="16" fill="{C_BG_PANEL}" opacity="0.6"/>')

    # 标题
    parts.append(f'<circle cx="130" cy="115" r="10" fill="{C_LASER}" filter="url(#laserGlow)"/>')
    parts.append(f'<text x="155" y="122" font-family="Source Han Sans SC, sans-serif" font-size="24" font-weight="700" fill="{C_WHITE}">FaceGuard</text>')
    parts.append(f'<text x="300" y="122" font-family="Source Han Sans SC, sans-serif" font-size="12" fill="{C_TEXT_DIM}">v2.1.2</text>')

    # 运行状态
    parts.append(f'<rect x="120" y="155" width="{W-240}" height="64" rx="8" fill="#ffffff" fill-opacity="0.04"/>')
    parts.append(f'<circle cx="150" cy="187" r="8" fill="{C_LASER}" filter="url(#laserGlow)"/>')
    parts.append(f'<circle cx="150" cy="187" r="14" fill="{C_LASER}" opacity="0.2"/>')
    parts.append(f'<text x="170" y="183" font-family="Source Han Sans SC, sans-serif" font-size="15" font-weight="600" fill="{C_LASER}">运行中</text>')
    parts.append(f'<text x="170" y="202" font-family="Source Han Sans SC, sans-serif" font-size="11" fill="{C_TEXT_DIM}">守护已激活 · 已注册 1 人</text>')

    # 快捷操作
    for ox, title, sub, color in [(120, "注册人脸", "采集多角度", C_LASER),
                                   (300, "设置", "调整参数", C_LASER_LT),
                                   (480, "测试邮件", "验证告警", C_AMBER)]:
        parts.append(f'<rect x="{ox}" y="240" width="160" height="76" rx="8" fill="#ffffff" fill-opacity="0.04"/>')
        parts.append(f'<circle cx="{ox+24}" cy="266" r="8" fill="{color}"/>')
        parts.append(f'<text x="{ox+42}" y="271" font-family="Source Han Sans SC, sans-serif" font-size="13" font-weight="600" fill="{C_WHITE}">{title}</text>')
        parts.append(f'<text x="{ox+16}" y="298" font-family="Source Han Sans SC, sans-serif" font-size="10" fill="{C_TEXT_HINT}">{sub}</text>')

    # 今日统计
    parts.append(f'<rect x="120" y="335" width="{W-240}" height="110" rx="8" fill="#ffffff" fill-opacity="0.04"/>')
    parts.append(f'<text x="140" y="360" font-family="Source Han Sans SC, sans-serif" font-size="13" font-weight="600" fill="{C_WHITE}">今日统计</text>')
    parts.append(f'<text x="160" y="390" font-family="Source Han Sans SC, sans-serif" font-size="11" fill="{C_TEXT_DIM}">解锁次数</text>')
    parts.append(f'<text x="160" y="425" font-family="Source Han Sans SC, sans-serif" font-size="30" font-weight="200" fill="{C_LASER}">23</text>')
    parts.append(f'<text x="340" y="390" font-family="Source Han Sans SC, sans-serif" font-size="11" fill="{C_TEXT_DIM}">失败告警</text>')
    parts.append(f'<text x="340" y="425" font-family="Source Han Sans SC, sans-serif" font-size="30" font-weight="200" fill="{C_RED}">1</text>')
    parts.append(f'<text x="520" y="390" font-family="Source Han Sans SC, sans-serif" font-size="11" fill="{C_TEXT_DIM}">学习样本</text>')
    parts.append(f'<text x="520" y="425" font-family="Source Han Sans SC, sans-serif" font-size="30" font-weight="200" fill="{C_LASER_LT}">12</text>')
    parts.append(f'<text x="140" y="475" font-family="Source Han Sans SC, sans-serif" font-size="10" fill="{C_TEXT_HINT}">最近解锁 14:32 · 阈值 0.58 · 模型 SFace</text>')

    # 退出按钮
    parts.append(f'<rect x="{W//2-60}" y="500" width="120" height="34" rx="17" fill="{C_RED}" fill-opacity="0.08" stroke="{C_RED}" stroke-opacity="0.3"/>')
    parts.append(f'<text x="{W//2}" y="522" font-family="Source Han Sans SC, sans-serif" font-size="13" fill="{C_RED_LT}" text-anchor="middle">退出</text>')

    return render_svg("\n".join(parts), "08_dashboard", W, H)


if __name__ == "__main__":
    shots = [
        ("1. 识别本人成功", shot_01_owner),
        ("2. 识别陌生人", shot_02_stranger),
        ("3. 身后入侵守护", shot_03_guardian),
        ("4. 离开锁屏休眠", shot_04_absence),
        ("5. 多帧确认中", shot_05_recognizing),
        ("6. 设置面板", shot_06_settings),
        ("7. 注册人脸", shot_07_enroll),
        ("8. 主面板", shot_08_dashboard),
    ]
    print("=" * 50)
    print("  FaceGuard · 简洁风格 + 蓝色激光点阵")
    print("=" * 50)
    ok = 0
    for name, fn in shots:
        if fn():
            ok += 1
            print(f"  [OK] {name}")
        else:
            print(f"  [FAIL] {name}")
    print(f"\n  完成: {ok}/{len(shots)} → {OUT}/")
