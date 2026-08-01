#!/usr/bin/env python3
"""
FaceGuard · Liquid Glass UI 截图生成器（v2 — 全盘美学重写）

设计语言（Tim Cook 审美 · Apple Liquid Glass 2025）：
  · 真实毛玻璃：feGaussianBlur 对彩色背景做真实模糊，不是单纯半透明
  · 镜面高光：feSpecularLighting 在玻璃边缘产生折射光斑
  · 液态折射：feTurbulence + feDisplacementMap 模拟玻璃微折射
  · 深度分层：多层玻璃叠加，每层模糊量不同
  · macOS 壁纸背景：紫/粉/橙/蓝/青 彩色渐变网格，透过玻璃可见
  · SF Pro 字体层级：思源黑体 SC，数字字重 200-900（修复乱码）
  · 动效可视化：呼吸光晕 / 脉冲环 / 扫描线泛光 / 粒子闪烁 / 流光边框
  · Apple 系统色：薄荷 #30D58C · 珊瑚 #FF453A · 琥珀 #FF9F0A · 蓝 #0A84FF · 紫 #BF5AF2
渲染：SVG + cairosvg @ 2x 高清
"""

from __future__ import annotations

import math
from pathlib import Path

import cairosvg

OUT = Path(__file__).parent / "screenshots"
OUT.mkdir(exist_ok=True)

# ═══════════════════════════════════════════════════════════════
#  Apple 系统色板（Liquid Glass 2025）
# ═══════════════════════════════════════════════════════════════
C_MINT    = "#30D58C"   # 本人成功
C_MINT_LT = "#5EEAB5"
C_CORAL   = "#FF453A"   # 陌生人失败
C_CORAL_LT= "#FF817A"
C_AMBER   = "#FF9F0A"   # 警告
C_AMBER_LT= "#FFBF47"
C_BLUE    = "#0A84FF"   # 离开/信息
C_BLUE_LT = "#409CFF"
C_PURPLE  = "#BF5AF2"   # 模型/设置
C_PURPLE_LT = "#D070FF"
C_PINK    = "#FF375F"

# 文字色
T_PRIMARY   = "#F5F5F7"   # 苹果白
T_SECONDARY = "#AEAEB2"   # 副文字
T_HINT      = "#636366"   # 提示
T_ON_GLASS  = "#FFFFFF"

# 玻璃色
GLASS_FILL     = "rgba(255,255,255,0.08)"
GLASS_STROKE   = "rgba(255,255,255,0.18)"
GLASS_INNER    = "rgba(255,255,255,0.06)"

# ═══════════════════════════════════════════════════════════════
#  SVG 设计系统：滤镜 / 渐变 / 背景壁纸
# ═══════════════════════════════════════════════════════════════

SVG_DEFS = """
<defs>
  <!-- ═══ 真实毛玻璃滤镜（背景模糊） ═══ -->
  <filter id="glassBlur" x="-30%" y="-30%" width="160%" height="160%">
    <feGaussianBlur in="SourceGraphic" stdDeviation="14"/>
  </filter>
  <filter id="glassBlurLg" x="-30%" y="-30%" width="160%" height="160%">
    <feGaussianBlur in="SourceGraphic" stdDeviation="28"/>
  </filter>
  <filter id="glassBlurSm" x="-20%" y="-20%" width="140%" height="140%">
    <feGaussianBlur in="SourceGraphic" stdDeviation="6"/>
  </filter>

  <!-- ═══ 镜面高光滤镜（边缘折射） ═══ -->
  <filter id="specular" x="-20%" y="-20%" width="140%" height="140%">
    <feGaussianBlur in="SourceAlpha" stdDeviation="2" result="blur"/>
    <feSpecularLighting in="blur" surfaceScale="5" specularConstant="0.9"
                        specularExponent="25" lighting-color="#ffffff" result="spec">
      <feDistantLight azimuth="225" elevation="55"/>
    </feSpecularLighting>
    <feComposite in="spec" in2="SourceAlpha" operator="in" result="specOut"/>
    <feComposite in="SourceGraphic" in2="specOut" operator="arithmetic"
                 k1="0" k2="1" k3="0.8" k4="0"/>
  </filter>

  <!-- ═══ 液态折射滤镜（微扭曲） ═══ -->
  <filter id="liquidRefract" x="-10%" y="-10%" width="120%" height="120%">
    <feTurbulence type="fractalNoise" baseFrequency="0.012 0.018"
                  numOctaves="2" seed="3" result="noise"/>
    <feDisplacementMap in="SourceGraphic" in2="noise" scale="6"
                       xChannelSelector="R" yChannelSelector="G"/>
  </filter>

  <!-- ═══ 发光 / 泛光滤镜 ═══ -->
  <filter id="bloom" x="-50%" y="-50%" width="200%" height="200%">
    <feGaussianBlur in="SourceGraphic" stdDeviation="4" result="blur"/>
    <feMerge>
      <feMergeNode in="blur"/>
      <feMergeNode in="blur"/>
      <feMergeNode in="SourceGraphic"/>
    </feMerge>
  </filter>
  <filter id="bloomStrong" x="-80%" y="-80%" width="260%" height="260%">
    <feGaussianBlur in="SourceGraphic" stdDeviation="10" result="blur"/>
    <feMerge>
      <feMergeNode in="blur"/>
      <feMergeNode in="blur"/>
      <feMergeNode in="blur"/>
      <feMergeNode in="SourceGraphic"/>
    </feMerge>
  </filter>
  <filter id="softGlow" x="-50%" y="-50%" width="200%" height="200%">
    <feGaussianBlur in="SourceGraphic" stdDeviation="3" result="blur"/>
    <feMerge>
      <feMergeNode in="blur"/>
      <feMergeNode in="SourceGraphic"/>
    </feMerge>
  </filter>

  <!-- ═══ 背景壁纸渐变（macOS Sonoma 风格彩色网格） ═══ -->
  <linearGradient id="wallpaperBase" x1="0%" y1="0%" x2="100%" y2="100%">
    <stop offset="0%"  stop-color="#1A1033"/>
    <stop offset="35%" stop-color="#2D1B4E"/>
    <stop offset="65%" stop-color="#1E1A3D"/>
    <stop offset="100%" stop-color="#0D0F1E"/>
  </linearGradient>

  <!-- 彩色光斑 -->
  <radialGradient id="blobPurple" cx="50%" cy="50%" r="50%">
    <stop offset="0%"  stop-color="#BF5AF2" stop-opacity="0.7"/>
    <stop offset="100%" stop-color="#BF5AF2" stop-opacity="0"/>
  </radialGradient>
  <radialGradient id="blobPink" cx="50%" cy="50%" r="50%">
    <stop offset="0%"  stop-color="#FF375F" stop-opacity="0.55"/>
    <stop offset="100%" stop-color="#FF375F" stop-opacity="0"/>
  </radialGradient>
  <radialGradient id="blobOrange" cx="50%" cy="50%" r="50%">
    <stop offset="0%"  stop-color="#FF9F0A" stop-opacity="0.5"/>
    <stop offset="100%" stop-color="#FF9F0A" stop-opacity="0"/>
  </radialGradient>
  <radialGradient id="blobBlue" cx="50%" cy="50%" r="50%">
    <stop offset="0%"  stop-color="#0A84FF" stop-opacity="0.5"/>
    <stop offset="100%" stop-color="#0A84FF" stop-opacity="0"/>
  </radialGradient>
  <radialGradient id="blobMint" cx="50%" cy="50%" r="50%">
    <stop offset="0%"  stop-color="#30D58C" stop-opacity="0.4"/>
    <stop offset="100%" stop-color="#30D58C" stop-opacity="0"/>
  </radialGradient>

  <!-- ═══ 玻璃面板材质 ═══ -->
  <linearGradient id="glassFill" x1="0%" y1="0%" x2="0%" y2="100%">
    <stop offset="0%"  stop-color="#ffffff" stop-opacity="0.14"/>
    <stop offset="50%" stop-color="#ffffff" stop-opacity="0.06"/>
    <stop offset="100%" stop-color="#ffffff" stop-opacity="0.03"/>
  </linearGradient>
  <linearGradient id="glassHighlight" x1="0%" y1="0%" x2="0%" y2="100%">
    <stop offset="0%"  stop-color="#ffffff" stop-opacity="0.35"/>
    <stop offset="30%" stop-color="#ffffff" stop-opacity="0.08"/>
    <stop offset="100%" stop-color="#ffffff" stop-opacity="0"/>
  </linearGradient>
  <linearGradient id="glassEdge" x1="0%" y1="0%" x2="100%" y2="100%">
    <stop offset="0%"  stop-color="#ffffff" stop-opacity="0.4"/>
    <stop offset="50%" stop-color="#ffffff" stop-opacity="0.1"/>
    <stop offset="100%" stop-color="#ffffff" stop-opacity="0.25"/>
  </linearGradient>

  <!-- ═══ 强调色按钮渐变 ═══ -->
  <linearGradient id="btnMint" x1="0%" y1="0%" x2="0%" y2="100%">
    <stop offset="0%"  stop-color="#5EEAB5"/>
    <stop offset="100%" stop-color="#28B574"/>
  </linearGradient>
  <linearGradient id="btnPurple" x1="0%" y1="0%" x2="0%" y2="100%">
    <stop offset="0%"  stop-color="#D070FF"/>
    <stop offset="100%" stop-color="#9B30DC"/>
  </linearGradient>

  <!-- ═══ 流光边框（彩虹渐变） ═══ -->
  <linearGradient id="rainbowBorder" x1="0%" y1="0%" x2="100%" y2="100%">
    <stop offset="0%"   stop-color="#30D58C"/>
    <stop offset="25%"  stop-color="#5EEAB5"/>
    <stop offset="50%"  stop-color="#0A84FF"/>
    <stop offset="75%"  stop-color="#BF5AF2"/>
    <stop offset="100%" stop-color="#FF375F"/>
  </linearGradient>

  <!-- ═══ 扫描线渐变 ═══ -->
  <linearGradient id="scanGrad" x1="0%" y1="0%" x2="0%" y2="100%">
    <stop offset="0%"   stop-color="#5EEAB5" stop-opacity="0"/>
    <stop offset="50%"  stop-color="#5EEAB5" stop-opacity="1"/>
    <stop offset="100%" stop-color="#5EEAB5" stop-opacity="0"/>
  </linearGradient>

  <!-- ═══ 阴影滤镜 ═══ -->
  <filter id="dropShadow" x="-20%" y="-20%" width="140%" height="140%">
    <feDropShadow dx="0" dy="8" stdDeviation="16" flood-color="#000000" flood-opacity="0.4"/>
  </filter>
  <filter id="dropShadowSm" x="-20%" y="-20%" width="140%" height="140%">
    <feDropShadow dx="0" dy="4" stdDeviation="8" flood-color="#000000" flood-opacity="0.3"/>
  </filter>
  <filter id="txtShadow" x="-50%" y="-50%" width="200%" height="200%">
    <feDropShadow dx="0" dy="1" stdDeviation="2" flood-color="#000000" flood-opacity="0.6"/>
  </filter>
</defs>
"""


# ═══════════════════════════════════════════════════════════════
#  组件工厂
# ═══════════════════════════════════════════════════════════════

def make_wallpaper(w: int, h: int) -> str:
    """macOS 风格彩色壁纸背景：大色块光斑 + 深色底 + 微粒纹理。"""
    return f"""
  <!-- 深色底 -->
  <rect width="{w}" height="{h}" fill="url(#wallpaperBase)"/>
  <!-- 彩色光斑（大模糊，模拟渐变网格） -->
  <ellipse cx="{w*0.15}" cy="{h*0.20}" rx="{w*0.35}" ry="{h*0.35}" fill="url(#blobPurple)" filter="url(#glassBlurLg)"/>
  <ellipse cx="{w*0.85}" cy="{h*0.15}" rx="{w*0.30}" ry="{h*0.30}" fill="url(#blobPink)" filter="url(#glassBlurLg)"/>
  <ellipse cx="{w*0.80}" cy="{h*0.80}" rx="{w*0.35}" ry="{h*0.35}" fill="url(#blobOrange)" filter="url(#glassBlurLg)"/>
  <ellipse cx="{w*0.20}" cy="{h*0.85}" rx="{w*0.30}" ry="{h*0.30}" fill="url(#blobBlue)" filter="url(#glassBlurLg)"/>
  <ellipse cx="{w*0.50}" cy="{h*0.50}" rx="{w*0.25}" ry="{h*0.25}" fill="url(#blobMint)" filter="url(#glassBlurLg)"/>
  <!-- 微粒噪点（模拟壁纸纹理） -->
  <rect width="{w}" height="{h}" fill="url(#wallpaperBase)" opacity="0.15"/>
"""


def glass_panel(x: float, y: float, w: float, h: float, r: float = 20,
                blur_bg: bool = True, shadow: bool = True) -> str:
    """真实液态玻璃面板：背景模糊 + 半透明 + 顶部高光 + 镜面边框 + 投影。"""
    parts = []
    filt = ' filter="url(#dropShadow)"' if shadow else ''
    clip_id = f"clip_{int(x)}_{int(y)}_{int(w)}_{int(h)}"
    parts.append(f"""
  <!-- 玻璃面板 @({x:.0f},{y:.0f}) {w:.0f}x{h:.0f} -->
  <defs>
    <clipPath id="{clip_id}">
      <rect x="{x}" y="{y}" width="{w}" height="{h}" rx="{r}"/>
    </clipPath>
  </defs>
  <g{filt}>""")
    if blur_bg:
        # 模糊背景层（透过玻璃看到的彩色背景）
        parts.append(f"""
    <g clip-path="url(#{clip_id})">
      <!-- 模糊的彩色背景 -->
      <rect x="{x}" y="{y}" width="{w}" height="{h}" fill="url(#wallpaperBase)"/>
      <ellipse cx="{x+w*0.2}" cy="{y+h*0.3}" rx="{w*0.4}" ry="{h*0.4}" fill="url(#blobPurple)" filter="url(#glassBlur)"/>
      <ellipse cx="{x+w*0.8}" cy="{y+h*0.7}" rx="{w*0.35}" ry="{h*0.35}" fill="url(#blobBlue)" filter="url(#glassBlur)"/>
      <!-- 玻璃半透明叠层 -->
      <rect x="{x}" y="{y}" width="{w}" height="{h}" fill="url(#glassFill)"/>
      <!-- 顶部镜面高光 -->
      <rect x="{x}" y="{y}" width="{w}" height="{h*0.5}" rx="{r}" fill="url(#glassHighlight)"/>
    </g>""")
    else:
        parts.append(f"""
    <rect x="{x}" y="{y}" width="{w}" height="{h}" rx="{r}" fill="url(#glassFill)"/>
    <rect x="{x}" y="{y}" width="{w}" height="{h*0.4}" rx="{r}" fill="url(#glassHighlight)"/>""")
    # 边框（双层：外亮内暗）
    parts.append(f"""
    <rect x="{x}" y="{y}" width="{w}" height="{h}" rx="{r}" fill="none"
          stroke="url(#glassEdge)" stroke-width="1.5"/>
    <rect x="{x+1.5}" y="{y+1.5}" width="{w-3}" height="{h-3}" rx="{r-1.5}" fill="none"
          stroke="#ffffff" stroke-opacity="0.05" stroke-width="1"/>
  </g>""")
    return "\n".join(parts)


def text(x: float, y: float, content: str, size: float = 14, weight: int = 400,
         color: str = T_PRIMARY, opacity: float = 1.0, anchor: str = "start",
         spacing: float = 0, shadow: bool = False) -> str:
    """SF Pro 风格文字（思源黑体 SC，数字字重 200-900）。"""
    ls = f' letter-spacing="{spacing}"' if spacing else ""
    filt = ' filter="url(#txtShadow)"' if shadow else ""
    return f'<text x="{x}" y="{y}" font-family="Source Han Sans SC, Noto Sans CJK SC, sans-serif" font-size="{size}" font-weight="{weight}" fill="{color}" fill-opacity="{opacity}" text-anchor="{anchor}"{ls}{filt}>{content}</text>'


_halo_counter = [0]


def halo(cx: float, cy: float, r: float, color: str, opacity: float = 0.6) -> str:
    """呼吸光晕（径向渐变）。每次调用生成唯一 ID 避免冲突。"""
    _halo_counter[0] += 1
    gid = f"halo_{_halo_counter[0]}"
    return f"""
  <defs>
    <radialGradient id="{gid}" cx="50%" cy="50%" r="50%">
      <stop offset="0%"  stop-color="{color}" stop-opacity="{opacity}"/>
      <stop offset="40%" stop-color="{color}" stop-opacity="{opacity*0.4}"/>
      <stop offset="100%" stop-color="{color}" stop-opacity="0"/>
    </radialGradient>
  </defs>
  <circle cx="{cx}" cy="{cy}" r="{r}" fill="url(#{gid})" filter="url(#bloomStrong)"/>"""


def pulse_ring(cx: float, cy: float, r: float, color: str, width: float = 2) -> str:
    """脉冲环（多层渐隐圆环，模拟动画扩散）。"""
    rings = []
    for i, (offset, op) in enumerate([(0, 0.9), (8, 0.5), (18, 0.25), (30, 0.1)]):
        rings.append(
            f'<circle cx="{cx}" cy="{cy}" r="{r+offset}" fill="none" '
            f'stroke="{color}" stroke-width="{width}" stroke-opacity="{op}" '
            f'filter="url(#softGlow)"/>'
        )
    return "\n".join(rings)


def scan_line(x: float, y: float, w: float, h: float, color: str = C_MINT_LT,
              pos: float = 0.4) -> str:
    """扫描线 + 泛光带（模拟动画中一帧）。"""
    ly = y + h * pos
    return f"""
  <!-- 扫描线泛光带 -->
  <rect x="{x}" y="{y}" width="{w}" height="{h}" fill="none"/>
  <rect x="{x}" y="{ly-20}" width="{w}" height="40" fill="{color}" opacity="0.08" filter="url(#glassBlur)"/>
  <rect x="{x}" y="{ly-8}" width="{w}" height="16" fill="{color}" opacity="0.2" filter="url(#glassBlurSm)"/>
  <!-- 主扫描线 -->
  <rect x="{x}" y="{ly-1}" width="{w}" height="2" fill="{color}" filter="url(#bloom)"/>"""


def face_landmarks(cx: float, cy: float, scale: float = 1, color: str = C_MINT_LT) -> str:
    """发光关键点 + 连线（5点：双眼/鼻/嘴角）。"""
    pts = {
        "re": (cx - 30*scale, cy - 15*scale),
        "le": (cx + 30*scale, cy - 15*scale),
        "n":  (cx,             cy + 5*scale),
        "rm": (cx - 22*scale, cy + 35*scale),
        "lm": (cx + 22*scale, cy + 35*scale),
    }
    parts = ["<!-- 关键点连线 -->"]
    pairs = [("re","le"),("le","n"),("n","rm"),("n","lm"),("rm","lm")]
    for a, b in pairs:
        parts.append(f'<line x1="{pts[a][0]}" y1="{pts[a][1]}" x2="{pts[b][0]}" y2="{pts[b][1]}" '
                     f'stroke="{color}" stroke-width="1" stroke-opacity="0.35"/>')
    parts.append("<!-- 发光关键点 -->")
    for name, (px, py) in pts.items():
        parts.append(f'<circle cx="{px}" cy="{py}" r="8" fill="{color}" opacity="0.25" filter="url(#bloom)"/>')
        parts.append(f'<circle cx="{px}" cy="{py}" r="3" fill="#ffffff" filter="url(#softGlow)"/>')
    return "\n".join(parts)


def toggle_switch(x: float, y: float, on: bool, color: str = C_MINT) -> str:
    """iOS 风格液态玻璃开关。"""
    if on:
        track_fill = color
        knob_cx = x + 26
    else:
        track_fill = "rgba(120,120,128,0.32)"
        knob_cx = x + 4
    return f"""
  <rect x="{x}" y="{y}" width="50" height="30" rx="15" fill="{track_fill}" opacity="0.85" filter="url(#dropShadowSm)"/>
  <circle cx="{knob_cx}" cy="{y+15}" r="12" fill="#ffffff" filter="url(#softGlow)"/>"""


def progress_bar(x: float, y: float, w: float, h: float, pct: float,
                 color: str = C_MINT) -> str:
    """液态进度条。"""
    fill_w = w * pct / 100
    gid = f"pg_{int(x)}_{int(y)}"
    return f"""
  <defs>
    <linearGradient id="{gid}" x1="0%" y1="0%" x2="100%" y2="0%">
      <stop offset="0%"  stop-color="{color}" stop-opacity="0.7"/>
      <stop offset="100%" stop-color="{color}" stop-opacity="1"/>
    </linearGradient>
  </defs>
  <rect x="{x}" y="{y}" width="{w}" height="{h}" rx="{h/2}" fill="rgba(255,255,255,0.1)"/>
  <rect x="{x}" y="{y}" width="{fill_w}" height="{h}" rx="{h/2}" fill="url(#{gid})" filter="url(#bloom)"/>"""


def sparkle(cx: float, cy: float, r: float = 3, color: str = "#ffffff") -> str:
    """四角星粒子（闪烁效果）。"""
    return f'<path d="M{cx},{cy-r} L{cx+r*0.3},{cy-r*0.3} L{cx+r},{cy} L{cx+r*0.3},{cy+r*0.3} L{cx},{cy+r} L{cx-r*0.3},{cy+r*0.3} L{cx-r},{cy} L{cx-r*0.3},{cy-r*0.3} Z" fill="{color}" opacity="0.7" filter="url(#softGlow)"/>'


def face_silhouette(cx: float, cy: float, scale: float = 1, color: str = "#2A2A3E") -> str:
    """人脸剪影（头+肩轮廓）。"""
    return f"""
  <ellipse cx="{cx}" cy="{cy-30*scale}" rx="{55*scale}" ry="{70*scale}" fill="{color}" opacity="0.7"/>
  <path d="M{cx-75*scale},{cy+80*scale} Q{cx-75*scale},{cy+20*scale} {cx},{cy+20*scale} Q{cx+75*scale},{cy+20*scale} {cx+75*scale},{cy+80*scale} Z" fill="{color}" opacity="0.7"/>"""


def status_pill(x: float, y: float, w: float, h: float, dot_color: str,
                label: str, sublabel: str = "", sub_color: str = "") -> str:
    """顶部状态胶囊。"""
    parts = [glass_panel(x, y, w, h, r=h/2, shadow=False)]
    parts.append(f'<circle cx="{x+h/2}" cy="{y+h/2}" r="5" fill="{dot_color}" filter="url(#bloom)"/>')
    parts.append(f'<circle cx="{x+h/2}" cy="{y+h/2}" r="10" fill="{dot_color}" opacity="0.25" filter="url(#bloom)"/>')
    parts.append(text(x + h/2 + 14, y + h/2 + 5, label, 14, 700, T_ON_GLASS, shadow=True))
    if sublabel:
        sc = sub_color or dot_color
        parts.append(text(x + h/2 + 14 + len(label)*12, y + h/2 + 5, f"· {sublabel}", 11, 500, sc))
    return "\n".join(parts)


def render_svg(svg_content: str, filename: str, w: int, h: int) -> bool:
    """生成 SVG + 渲染 PNG @ 2x。"""
    svg = f'''<?xml version="1.0" encoding="UTF-8"?>
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {w} {h}" width="{w}" height="{h}">
{SVG_DEFS}
{make_wallpaper(w, h)}
{svg_content}
</svg>'''
    svg_path = OUT / f"{filename}.svg"
    svg_path.write_text(svg, encoding="utf-8")
    png_path = OUT / f"{filename}.png"
    try:
        cairosvg.svg2png(
            bytestring=svg.encode("utf-8"),
            write_to=str(png_path),
            output_width=w * 2,
            output_height=h * 2,
        )
        return True
    except Exception as e:
        print(f"  渲染失败 {filename}: {e}")
        return False


# ═══════════════════════════════════════════════════════════════
#  8 个核心界面
# ═══════════════════════════════════════════════════════════════

def shot_01_recognize_owner() -> bool:
    """识别本人成功：绿色呼吸光晕 + 流光人脸框 + 脉冲环。"""
    W, H = 800, 600
    cx, cy = 400, 270
    content = f"""
  <!-- 摄像头画面暗框 -->
  <rect x="30" y="30" width="{W-60}" height="{H-60}" rx="28" fill="#000000" opacity="0.25" filter="url(#dropShadow)"/>

  <!-- 人脸剪影 -->
  {face_silhouette(cx, cy, 1.3, "#3A3A5C")}

  <!-- 呼吸光晕（薄荷绿） -->
  {halo(cx, cy-10, 200, C_MINT, 0.5)}

  <!-- 脉冲环（3层扩散，模拟动画） -->
  {pulse_ring(cx, cy-10, 130, C_MINT, 2.5)}
  {pulse_ring(cx, cy-10, 100, C_MINT_LT, 2)}

  <!-- 流光人脸框（圆角 + 彩虹边框 + 高光） -->
  <rect x="{cx-110}" y="{cy-130}" width="220" height="230" rx="22" fill="none"
        stroke="url(#rainbowBorder)" stroke-width="3" filter="url(#bloom)"/>
  <rect x="{cx-110}" y="{cy-130}" width="220" height="230" rx="22" fill="none"
        stroke="#ffffff" stroke-width="1" stroke-opacity="0.5"/>

  <!-- 关键点 -->
  {face_landmarks(cx, cy-10, 1.3, C_MINT_LT)}

  <!-- 四角装饰角标 -->
  <path d="M{cx-120},{cy-120} L{cx-120},{cy-105} M{cx-120},{cy-120} L{cx-105},{cy-120}" stroke="{C_MINT}" stroke-width="3" stroke-linecap="round" filter="url(#bloom)"/>
  <path d="M{cx+120},{cy-120} L{cx+120},{cy-105} M{cx+120},{cy-120} L{cx+105},{cy-120}" stroke="{C_MINT}" stroke-width="3" stroke-linecap="round" filter="url(#bloom)"/>
  <path d="M{cx-120},{cy+120} L{cx-120},{cy+105} M{cx-120},{cy+120} L{cx-105},{cy+120}" stroke="{C_MINT}" stroke-width="3" stroke-linecap="round" filter="url(#bloom)"/>
  <path d="M{cx+120},{cy+120} L{cx+120},{cy+105} M{cx+120},{cy+120} L{cx+105},{cy+120}" stroke="{C_MINT}" stroke-width="3" stroke-linecap="round" filter="url(#bloom)"/>

  <!-- 顶部状态胶囊 -->
  {glass_panel(30, 40, 300, 52, 26)}
  <circle cx="56" cy="66" r="6" fill="{C_MINT}" filter="url(#bloom)"/>
  <circle cx="56" cy="66" r="12" fill="{C_MINT}" opacity="0.25"/>
  {text(72, 71, "FaceGuard", 17, 700, T_ON_GLASS, shadow=True)}
  {text(186, 71, "已激活", 12, 500, C_MINT_LT)}

  <!-- 右上角置信度 -->
  {glass_panel(570, 40, 200, 52, 26)}
  {text(590, 71, "置信度", 12, 500, T_SECONDARY)}
  {text(700, 71, "99.2%", 17, 700, C_MINT, anchor="end", shadow=True)}

  <!-- 底部状态栏 -->
  {glass_panel(30, H-80, W-60, 50, 18)}
  <circle cx="58" cy="{H-55}" r="5" fill="{C_MINT}" filter="url(#bloom)"/>
  {text(74, H-50, "✓ 识别成功 · 已解锁", 15, 700, C_MINT_LT, shadow=True)}
  {text(W-50, H-50, "FaceGuard v2.1", 11, 400, T_HINT, anchor="end")}

  <!-- 粒子闪烁 -->
  {sparkle(180, 200, 4, C_MINT_LT)}
  {sparkle(620, 180, 3, C_MINT_LT)}
  {sparkle(150, 400, 3, "#ffffff")}
  {sparkle(650, 420, 4, C_MINT_LT)}
  {sparkle(580, 300, 2, "#ffffff")}"""
    return render_svg(content, "01_recognize_owner", W, H)


def shot_02_recognize_stranger() -> bool:
    """识别陌生人失败：红色警告光晕 + 警告框。"""
    W, H = 800, 600
    cx, cy = 400, 270
    content = f"""
  <rect x="30" y="30" width="{W-60}" height="{H-60}" rx="28" fill="#000000" opacity="0.25" filter="url(#dropShadow)"/>
  {face_silhouette(cx, cy, 1.3, "#5C2A2A")}

  <!-- 警告光晕（珊瑚红） -->
  {halo(cx, cy-10, 200, C_CORAL, 0.5)}
  {pulse_ring(cx, cy-10, 130, C_CORAL, 2.5)}

  <!-- 人脸框（红色警告） -->
  <rect x="{cx-110}" y="{cy-130}" width="220" height="230" rx="22" fill="none"
        stroke="{C_CORAL}" stroke-width="3" filter="url(#bloom)"/>
  <rect x="{cx-110}" y="{cy-130}" width="220" height="230" rx="22" fill="none"
        stroke="{C_CORAL_LT}" stroke-width="1" stroke-opacity="0.5"/>

  {face_landmarks(cx, cy-10, 1.3, C_CORAL_LT)}

  <!-- 警告角标 -->
  <path d="M{cx-120},{cy-120} L{cx-120},{cy-105} M{cx-120},{cy-120} L{cx-105},{cy-120}" stroke="{C_CORAL}" stroke-width="3" stroke-linecap="round" filter="url(#bloom)"/>
  <path d="M{cx+120},{cy-120} L{cx+120},{cy-105} M{cx+120},{cy-120} L{cx+105},{cy-120}" stroke="{C_CORAL}" stroke-width="3" stroke-linecap="round" filter="url(#bloom)"/>
  <path d="M{cx-120},{cy+120} L{cx-120},{cy+105} M{cx-120},{cy+120} L{cx-105},{cy+120}" stroke="{C_CORAL}" stroke-width="3" stroke-linecap="round" filter="url(#bloom)"/>
  <path d="M{cx+120},{cy+120} L{cx+120},{cy+105} M{cx+120},{cy+120} L{cx+105},{cy+120}" stroke="{C_CORAL}" stroke-width="3" stroke-linecap="round" filter="url(#bloom)"/>

  <!-- 顶部状态 -->
  {glass_panel(30, 40, 300, 52, 26)}
  <circle cx="56" cy="66" r="6" fill="{C_CORAL}" filter="url(#bloom)"/>
  <circle cx="56" cy="66" r="12" fill="{C_CORAL}" opacity="0.25"/>
  {text(72, 71, "FaceGuard", 17, 700, T_ON_GLASS, shadow=True)}
  {text(186, 71, "警告", 12, 500, C_CORAL_LT)}

  <!-- 右上角抓拍状态 -->
  {glass_panel(540, 40, 230, 52, 26)}
  {text(560, 71, "已抓拍 #2", 12, 500, C_AMBER_LT)}
  {text(750, 71, "邮件已发送", 11, 500, C_MINT_LT, anchor="end")}

  <!-- 底部状态 -->
  {glass_panel(30, H-80, W-60, 50, 18)}
  <circle cx="58" cy="{H-55}" r="5" fill="{C_CORAL}" filter="url(#bloom)"/>
  {text(74, H-50, "✕ 识别失败 · 已抓拍并发送告警邮件", 15, 700, C_CORAL_LT, shadow=True)}
  {text(W-50, H-50, "陌生人 · 相似度 12%", 11, 400, T_HINT, anchor="end")}

  {sparkle(180, 200, 4, C_CORAL_LT)}
  {sparkle(620, 180, 3, C_CORAL_LT)}"""
    return render_svg(content, "02_recognize_stranger", W, H)


def shot_03_guardian_intruder() -> bool:
    """身后入侵守护：双人脸（本人安全 + 入侵者警告）。"""
    W, H = 800, 600
    content = f"""
  <rect x="30" y="30" width="{W-60}" height="{H-60}" rx="28" fill="#000000" opacity="0.25" filter="url(#dropShadow)"/>

  <!-- 本人（左侧，安全） -->
  {face_silhouette(250, 290, 1.0, "#3A3A5C")}
  {halo(250, 270, 120, C_MINT, 0.4)}
  {pulse_ring(250, 270, 80, C_MINT, 2)}
  <rect x="170" y="190" width="160" height="170" rx="18" fill="none" stroke="{C_MINT}" stroke-width="2.5" filter="url(#bloom)"/>
  {face_landmarks(250, 270, 1.0, C_MINT_LT)}

  <!-- 入侵者（右侧，警告） -->
  {face_silhouette(560, 260, 1.05, "#5C3A1A")}
  {halo(560, 240, 130, C_AMBER, 0.5)}
  {pulse_ring(560, 240, 90, C_AMBER, 2.5)}
  <rect x="475" y="155" width="170" height="180" rx="18" fill="none" stroke="{C_AMBER}" stroke-width="3" filter="url(#bloom)"/>
  {face_landmarks(560, 240, 1.05, C_AMBER_LT)}

  <!-- 中间连接线（检测关系） -->
  <line x1="330" y1="280" x2="475" y2="250" stroke="{C_AMBER}" stroke-width="1.5" stroke-dasharray="6 4" opacity="0.5" filter="url(#bloom)"/>
  {text(400, 250, "身后检测", 12, 700, C_AMBER_LT, anchor="middle", shadow=True)}

  <!-- 顶部状态 -->
  {glass_panel(30, 40, 300, 52, 26)}
  <circle cx="56" cy="66" r="6" fill="{C_AMBER}" filter="url(#bloom)"/>
  {text(72, 71, "FaceGuard", 17, 700, T_ON_GLASS, shadow=True)}
  {text(186, 71, "守护警告", 12, 500, C_AMBER_LT)}

  {glass_panel(440, 40, 330, 52, 26)}
  {text(460, 71, "身后出现 1 人", 13, 700, C_AMBER_LT, shadow=True)}
  {text(750, 71, "已邮件告警", 11, 500, C_MINT_LT, anchor="end")}

  <!-- 底部状态 -->
  {glass_panel(30, H-80, W-60, 50, 18)}
  <circle cx="58" cy="{H-55}" r="5" fill="{C_AMBER}" filter="url(#bloom)"/>
  {text(74, H-50, "⚠ 守护模式 · 检测到身后他人", 15, 700, C_AMBER_LT, shadow=True)}"""
    return render_svg(content, "03_guardian_intruder", W, H)


def shot_04_absence() -> bool:
    """离开锁屏休眠：倒计时 + 进度环。"""
    W, H = 800, 600
    cx, cy = 400, 280
    content = f"""
  <rect x="30" y="30" width="{W-60}" height="{H-60}" rx="28" fill="#000000" opacity="0.35" filter="url(#dropShadow)"/>

  <!-- 蓝色光晕 -->
  {halo(cx, cy, 200, C_BLUE, 0.3)}

  <!-- 大数字倒计时 -->
  {text(cx, cy-20, "5:00", 96, 200, C_BLUE_LT, anchor="middle", shadow=True)}
  {text(cx, cy+30, "后进入休眠", 18, 500, T_SECONDARY, anchor="middle")}

  <!-- 进度环 -->
  <circle cx="{cx}" cy="{cy+110}" r="45" fill="none" stroke="rgba(255,255,255,0.1)" stroke-width="8"/>
  <circle cx="{cx}" cy="{cy+110}" r="45" fill="none" stroke="{C_BLUE}" stroke-width="8"
          stroke-linecap="round" stroke-dasharray="283" stroke-dashoffset="85"
          transform="rotate(-90 {cx} {cy+110})" filter="url(#bloom)"/>

  <!-- 顶部状态 -->
  {glass_panel(30, 40, 300, 52, 26)}
  <circle cx="56" cy="66" r="6" fill="{C_BLUE}" filter="url(#bloom)"/>
  {text(72, 71, "FaceGuard", 17, 700, T_ON_GLASS, shadow=True)}
  {text(186, 71, "离开模式", 12, 500, C_BLUE_LT)}

  {glass_panel(500, 40, 270, 52, 26)}
  {text(520, 71, "已锁屏 · 等待休眠", 13, 500, C_BLUE_LT, shadow=True)}

  <!-- 底部状态 -->
  {glass_panel(30, H-80, W-60, 50, 18)}
  <circle cx="58" cy="{H-55}" r="5" fill="{C_BLUE}" filter="url(#bloom)"/>
  {text(74, H-50, "用户已离开 · 已锁屏 · 5 分钟后休眠", 15, 700, C_BLUE_LT, shadow=True)}

  {sparkle(200, 150, 3, C_BLUE_LT)}
  {sparkle(600, 130, 4, C_BLUE_LT)}
  {sparkle(150, 450, 3, "#ffffff")}"""
    return render_svg(content, "04_absence", W, H)


def shot_05_recognizing() -> bool:
    """多帧确认中：扫描线 + 进度。"""
    W, H = 800, 600
    cx, cy = 270, 260
    content = f"""
  <rect x="30" y="30" width="{W-60}" height="{H-60}" rx="28" fill="#000000" opacity="0.25" filter="url(#dropShadow)"/>
  {face_silhouette(cx, cy, 1.3, "#3A3A5C")}

  <!-- 扫描中光晕 -->
  {halo(cx, cy-10, 160, C_MINT_LT, 0.35)}

  <!-- 人脸框（虚线，扫描中） -->
  <rect x="{cx-110}" y="{cy-130}" width="220" height="230" rx="22" fill="none"
        stroke="{C_MINT_LT}" stroke-width="2" stroke-dasharray="10 6" opacity="0.8" filter="url(#bloom)"/>

  <!-- 扫描线 -->
  {scan_line(cx-110, cy-130, 220, 230, C_MINT_LT, 0.45)}

  {face_landmarks(cx, cy-10, 1.3, C_MINT_LT)}

  <!-- 右侧识别面板 -->
  {glass_panel(460, 150, 310, 280, 22)}
  {text(490, 195, "正在识别", 18, 700, T_PRIMARY, shadow=True)}
  {text(490, 220, "多帧确认确保安全", 12, 400, T_SECONDARY)}

  <!-- 帧确认进度 -->
  {text(490, 260, "多帧确认", 13, 500, T_SECONDARY)}
  {progress_bar(490, 270, 250, 8, 67, C_MINT_LT)}
  {text(740, 260, "2/3", 13, 700, C_MINT_LT, anchor="end")}

  <!-- 特征提取状态 -->
  {text(490, 305, "特征提取", 13, 500, T_SECONDARY)}
  {progress_bar(490, 315, 250, 8, 85, C_BLUE_LT)}
  {text(740, 305, "85%", 13, 700, C_BLUE_LT, anchor="end")}

  <!-- 活体检测 -->
  {text(490, 350, "活体检测", 13, 500, T_SECONDARY)}
  {progress_bar(490, 360, 250, 8, 92, C_PURPLE_LT)}
  {text(740, 350, "92%", 13, 700, C_PURPLE_LT, anchor="end")}

  <!-- 模型信息 -->
  {glass_panel(480, 390, 270, 28, 14, blur_bg=False, shadow=False)}
  {text(494, 408, "YuNet + SFace", 11, 500, T_SECONDARY)}

  <!-- 顶部状态 -->
  {glass_panel(30, 40, 300, 52, 26)}
  <circle cx="56" cy="66" r="6" fill="{C_MINT_LT}" filter="url(#bloom)"/>
  {text(72, 71, "FaceGuard", 17, 700, T_ON_GLASS, shadow=True)}
  {text(186, 71, "识别中", 12, 500, C_MINT_LT)}

  <!-- 底部状态 -->
  {glass_panel(30, H-80, W-60, 50, 18)}
  <circle cx="58" cy="{H-55}" r="5" fill="{C_MINT_LT}" filter="url(#bloom)"/>
  {text(74, H-50, "◌ 识别中 · 多帧确认 2/3", 15, 700, C_MINT_LT, shadow=True)}"""
    return render_svg(content, "05_recognizing", W, H)


def shot_06_settings() -> bool:
    """设置面板：液态玻璃 + 模型选择 + 自适应学习 + 邮件 + 离开。"""
    W, H = 900, 1180
    y = 0
    sections = []

    # 标题
    sections.append(f"""
  <!-- 标题区 -->
  {halo(80, 70, 50, C_MINT, 0.3)}
  {text(60, 70, "FaceGuard", 38, 900, C_MINT, shadow=True)}
  {text(62, 95, "Liquid Glass · 人脸解锁守护", 14, 400, T_SECONDARY)}
  {text(W-50, 70, "v2.1.0", 14, 500, T_SECONDARY, anchor="end")}
  {glass_panel(50, 110, W-100, 2, 1, blur_bg=False, shadow=False)}""")

    # === 识别引擎 ===
    y = 140
    sections.append(glass_panel(50, y, W-100, 140, 22))
    sections.append(f'<circle cx="76" cy="{y+30}" r="5" fill="{C_MINT}" filter="url(#bloom)"/>')
    sections.append(text(92, y+36, "识别引擎", 16, 700, T_PRIMARY, shadow=True))
    sections.append(text(180, y+36, "Recognition", 11, 400, T_HINT))
    # 输入行
    fields = [
        (y+72, "置信度阈值", "0.55", "0.3–0.8", C_MINT),
        (y+108, "确认帧数", "3", "帧", C_MINT),
    ]
    for fy, label, val, hint, c in fields:
        sections.append(text(76, fy, label, 13, 500, T_SECONDARY))
        sections.append(f'<rect x="210" y="{fy-16}" width="140" height="30" rx="8" fill="rgba(255,255,255,0.06)" stroke="rgba(255,255,255,0.12)"/>')
        sections.append(text(222, fy+4, val, 13, 700, T_PRIMARY))
        sections.append(text(360, fy+4, hint, 11, 400, T_HINT))
    sections.append(text(470, y+72, "摄像头序号", 13, 500, T_SECONDARY))
    sections.append(f'<rect x="610" y="{y+56}" width="80" height="30" rx="8" fill="rgba(255,255,255,0.06)" stroke="rgba(255,255,255,0.12)"/>')
    sections.append(text(622, y+76, "0", 13, 700, T_PRIMARY))
    sections.append(text(470, y+108, "识别帧率", 13, 500, T_SECONDARY))
    sections.append(f'<rect x="610" y="{y+92}" width="80" height="30" rx="8" fill="rgba(255,255,255,0.06)" stroke="rgba(255,255,255,0.12)"/>')
    sections.append(text(622, y+112, "15 fps", 13, 700, T_PRIMARY))

    # === 识别模型（三选一） ===
    y = 300
    sections.append(glass_panel(50, y, W-100, 170, 22))
    sections.append(f'<circle cx="76" cy="{y+30}" r="5" fill="{C_PURPLE}" filter="url(#bloom)"/>')
    sections.append(text(92, y+36, "识别模型", 16, 700, T_PRIMARY, shadow=True))
    sections.append(text(180, y+36, "Model · 三选一", 11, 400, T_HINT))

    # 三个模型卡片
    models = [
        (76, "YuNet + SFace", "默认 · 精度 99.5%", "38 MB · 平衡推荐", C_MINT, True),
        (330, "MobileFaceNet", "轻量 · 精度 99.0%", "5 MB · 老电脑友好", C_BLUE_LT, False),
        (584, "ArcFace ResNet50", "高精度 · 99.8%", "170 MB · 极致精度", C_PURPLE_LT, False),
    ]
    for mx, name, desc, size, color, selected in models:
        card_w = 250
        card_y = y + 56
        card_h = 96
        if selected:
            sections.append(f'<rect x="{mx}" y="{card_y}" width="{card_w}" height="{card_h}" rx="16" fill="{color}" fill-opacity="0.12" stroke="{color}" stroke-width="2" filter="url(#bloom)"/>')
            sections.append(f'<circle cx="{mx+20}" cy="{card_y+22}" r="4" fill="{color}" filter="url(#bloom)"/>')
            sections.append(text(mx+32, card_y+28, name, 14, 700, color, shadow=True))
        else:
            sections.append(f'<rect x="{mx}" y="{card_y}" width="{card_w}" height="{card_h}" rx="16" fill="rgba(255,255,255,0.04)" stroke="rgba(255,255,255,0.1)"/>')
            sections.append(f'<circle cx="{mx+20}" cy="{card_y+22}" r="4" fill="{T_HINT}"/>')
            sections.append(text(mx+32, card_y+28, name, 14, 500, T_PRIMARY))
        sections.append(text(mx+20, card_y+54, desc, 12, 400, T_SECONDARY))
        sections.append(text(mx+20, card_y+76, size, 11, 400, T_HINT))

    # === 自适应学习 ===
    y = 490
    sections.append(glass_panel(50, y, W-100, 170, 22))
    sections.append(f'<circle cx="76" cy="{y+30}" r="5" fill="{C_MINT_LT}" filter="url(#bloom)"/>')
    sections.append(text(92, y+36, "自适应学习", 16, 700, T_PRIMARY, shadow=True))
    sections.append(text(200, y+36, "Adaptive · 记忆脸部变化", 11, 400, T_HINT))
    sections.append(toggle_switch(W-130, y+22, True, C_MINT))
    sections.append(text(76, y+78, "成功解锁后增量学习", 13, 500, T_PRIMARY))
    sections.append(text(76, y+98, "程序自动记住你脸部变化（光线 / 角度 / 表情）", 11, 400, T_HINT))
    sections.append(text(76, y+134, "每用户最多", 13, 500, T_SECONDARY))
    sections.append(f'<rect x="200" y="{y+118}" width="80" height="30" rx="8" fill="rgba(255,255,255,0.06)" stroke="rgba(255,255,255,0.12)"/>')
    sections.append(text(212, y+138, "30", 13, 700, T_PRIMARY))
    sections.append(text(290, y+138, "个样本", 11, 400, T_HINT))
    sections.append(text(470, y+134, "冷却秒数", 13, 500, T_SECONDARY))
    sections.append(f'<rect x="610" y="{y+118}" width="80" height="30" rx="8" fill="rgba(255,255,255,0.06)" stroke="rgba(255,255,255,0.12)"/>')
    sections.append(text(622, y+138, "300", 13, 700, T_PRIMARY))

    # === 邮件告警 ===
    y = 680
    sections.append(glass_panel(50, y, W-100, 170, 22))
    sections.append(f'<circle cx="76" cy="{y+30}" r="5" fill="{C_AMBER}" filter="url(#bloom)"/>')
    sections.append(text(92, y+36, "邮件告警", 16, 700, T_PRIMARY, shadow=True))
    sections.append(text(180, y+36, "失败抓拍 / 入侵提醒", 11, 400, T_HINT))
    sections.append(text(76, y+78, "SMTP 服务器", 13, 500, T_SECONDARY))
    sections.append(f'<rect x="210" y="{y+62}" width="260" height="30" rx="8" fill="rgba(255,255,255,0.06)" stroke="rgba(255,255,255,0.12)"/>')
    sections.append(text(222, y+82, "smtp.qq.com", 13, 500, T_PRIMARY))
    sections.append(text(76, y+118, "发件邮箱", 13, 500, T_SECONDARY))
    sections.append(f'<rect x="210" y="{y+102}" width="340" height="30" rx="8" fill="rgba(255,255,255,0.06)" stroke="rgba(255,255,255,0.12)"/>')
    sections.append(text(222, y+122, "1247053973@qq.com", 13, 500, T_PRIMARY))
    sections.append(text(570, y+118, "授权码", 13, 500, T_SECONDARY))
    sections.append(f'<rect x="660" y="{y+102}" width="160" height="30" rx="8" fill="rgba(255,255,255,0.06)" stroke="rgba(255,255,255,0.12)"/>')
    sections.append(text(672, y+122, "●●●●●●●●", 13, 500, T_PRIMARY))
    sections.append(text(76, y+158, "告警冷却", 13, 500, T_SECONDARY))
    sections.append(f'<rect x="210" y="{y+142}" width="80" height="30" rx="8" fill="rgba(255,255,255,0.06)" stroke="rgba(255,255,255,0.12)"/>')
    sections.append(text(222, y+162, "60", 13, 700, T_PRIMARY))
    sections.append(text(300, y+162, "秒", 11, 400, T_HINT))

    # === 离开锁屏休眠 ===
    y = 870
    sections.append(glass_panel(50, y, W-100, 120, 22))
    sections.append(f'<circle cx="76" cy="{y+30}" r="5" fill="{C_BLUE}" filter="url(#bloom)"/>')
    sections.append(text(92, y+36, "离开锁屏休眠", 16, 700, T_PRIMARY, shadow=True))
    sections.append(text(220, y+36, "Presence", 11, 400, T_HINT))
    sections.append(text(76, y+80, "离开锁屏", 13, 500, T_SECONDARY))
    sections.append(f'<rect x="210" y="{y+64}" width="80" height="30" rx="8" fill="rgba(255,255,255,0.06)" stroke="rgba(255,255,255,0.12)"/>')
    sections.append(text(222, y+84, "300", 13, 700, T_PRIMARY))
    sections.append(text(300, y+84, "秒", 11, 400, T_HINT))
    sections.append(text(470, y+80, "锁屏休眠", 13, 500, T_SECONDARY))
    sections.append(f'<rect x="610" y="{y+64}" width="80" height="30" rx="8" fill="rgba(255,255,255,0.06)" stroke="rgba(255,255,255,0.12)"/>')
    sections.append(text(622, y+84, "300", 13, 700, T_PRIMARY))
    sections.append(text(700, y+84, "秒", 11, 400, T_HINT))

    # === 功能开关 ===
    y = 1010
    sections.append(glass_panel(50, y, W-100, 90, 22))
    sections.append(f'<circle cx="76" cy="{y+30}" r="5" fill="{C_PURPLE}" filter="url(#bloom)"/>')
    sections.append(text(92, y+36, "功能开关", 16, 700, T_PRIMARY, shadow=True))
    sections.append(text(76, y+76, "身后入侵守护", 13, 500, T_PRIMARY))
    sections.append(toggle_switch(W-130, y+62, True, C_MINT))
    sections.append(text(330, y+76, "注册表自启", 13, 500, T_PRIMARY))
    sections.append(toggle_switch(W-130-260, y+62, True, C_MINT))

    # 保存按钮
    sections.append(f'<rect x="{W//2-130}" y="1130" width="260" height="46" rx="23" fill="url(#btnMint)" filter="url(#dropShadow)"/>')
    sections.append(text(W//2, 1159, "保存设置", 16, 700, "#0A1A12", anchor="middle"))

    return render_svg("\n".join(sections), "06_settings_panel", W, H)


def shot_07_enroll() -> bool:
    """注册人脸流程：扫描引导 + 进度。"""
    W, H = 800, 600
    cx, cy = 400, 270
    content = f"""
  <rect x="30" y="30" width="{W-60}" height="{H-60}" rx="28" fill="#000000" opacity="0.25" filter="url(#dropShadow)"/>
  {face_silhouette(cx, cy, 1.35, "#3A3A5C")}

  <!-- 引导光晕 -->
  {halo(cx, cy-10, 180, C_PURPLE, 0.3)}

  <!-- 人脸框（圆角流光） -->
  <rect x="{cx-115}" y="{cy-135}" width="230" height="240" rx="22" fill="none"
        stroke="url(#rainbowBorder)" stroke-width="3" filter="url(#bloom)"/>

  <!-- 扫描线 -->
  {scan_line(cx-115, cy-135, 230, 240, C_PURPLE_LT, 0.35)}

  {face_landmarks(cx, cy-10, 1.35, C_PURPLE_LT)}

  <!-- 顶部状态 -->
  {glass_panel(30, 40, 300, 52, 26)}
  <circle cx="56" cy="66" r="6" fill="{C_PURPLE}" filter="url(#bloom)"/>
  {text(72, 71, "FaceGuard", 17, 700, T_ON_GLASS, shadow=True)}
  {text(186, 71, "注册中", 12, 500, C_PURPLE_LT)}

  <!-- 采集进度 -->
  {glass_panel(30, 105, 380, 48, 24)}
  {text(50, 135, "采集 5/8", 15, 700, C_PURPLE_LT, shadow=True)}
  {text(145, 135, "请正对摄像头", 12, 400, T_SECONDARY)}

  <!-- 角度引导 -->
  {glass_panel(430, 105, 340, 48, 24)}
  {text(450, 135, "← 正面 → 左侧 → 右侧", 12, 500, T_SECONDARY)}
  {text(750, 135, "当前: 正面", 11, 700, C_PURPLE_LT, anchor="end")}

  <!-- 底部进度条 -->
  {glass_panel(30, H-80, W-60, 50, 18)}
  {progress_bar(60, H-60, W-120, 10, 62.5, C_PURPLE_LT)}
  {text(60, H-88, "注册进度", 12, 500, T_SECONDARY)}
  {text(W-60, H-88, "62%", 14, 700, C_PURPLE_LT, anchor="end")}

  {sparkle(180, 200, 4, C_PURPLE_LT)}
  {sparkle(620, 180, 3, C_PURPLE_LT)}
  {sparkle(150, 400, 3, "#ffffff")}"""
    return render_svg(content, "07_enroll", W, H)


def shot_08_dashboard() -> bool:
    """主面板：系统状态 + 快捷操作 + 统计。"""
    W, H = 800, 600
    parts = []
    parts.append(glass_panel(80, 60, W-160, H-120, 28))
    parts.append(halo(130, 115, 35, C_MINT, 0.3))
    parts.append(f'<circle cx="130" cy="115" r="14" fill="{C_MINT}" filter="url(#bloom)"/>')
    parts.append(f'<circle cx="130" cy="115" r="24" fill="{C_MINT}" opacity="0.2" filter="url(#bloom)"/>')
    parts.append(text(158, 108, "FaceGuard", 28, 900, T_PRIMARY, shadow=True))
    parts.append(text(310, 108, "v2.1.0", 13, 400, T_HINT))

    # 运行状态卡片
    parts.append(glass_panel(120, 160, W-240, 80, 18))
    parts.append(f'<circle cx="155" cy="200" r="10" fill="{C_MINT}" filter="url(#bloom)"/>')
    parts.append(f'<circle cx="155" cy="200" r="20" fill="{C_MINT}" opacity="0.2" filter="url(#bloom)"/>')
    parts.append(pulse_ring(155, 200, 14, C_MINT, 1.5))
    parts.append(text(180, 194, "运行中", 18, 700, C_MINT_LT, shadow=True))
    parts.append(text(180, 216, "守护已激活 · 已注册 1 人", 12, 400, T_SECONDARY))
    parts.append(text(W-150, 200, "●", 20, 900, C_MINT, anchor="end"))

    # 三个快捷操作
    for ox, title, sub, color in [
        (120, "注册人脸", "采集多角度", C_MINT_LT),
        (300, "设置", "调整参数", C_PURPLE_LT),
        (480, "测试邮件", "验证告警", C_AMBER_LT),
    ]:
        parts.append(glass_panel(ox, 260, 180, 90, 16))
        parts.append(f'<circle cx="{ox+28}" cy="290" r="10" fill="{color}" filter="url(#bloom)"/>')
        parts.append(f'<circle cx="{ox+28}" cy="290" r="18" fill="{color}" opacity="0.2" filter="url(#bloom)"/>')
        parts.append(text(ox+48, 296, title, 15, 700, T_PRIMARY, shadow=True))
        parts.append(text(ox+20, 328, sub, 11, 400, T_HINT))

    # 今日统计
    parts.append(glass_panel(120, 370, W-240, 130, 18))
    parts.append(text(140, 400, "今日统计", 15, 700, T_PRIMARY, shadow=True))
    parts.append(text(160, 435, "解锁次数", 12, 500, T_SECONDARY))
    parts.append(text(160, 475, "23", 36, 900, C_MINT, shadow=True))
    parts.append(text(340, 435, "失败告警", 12, 500, T_SECONDARY))
    parts.append(text(340, 475, "1", 36, 900, C_CORAL, shadow=True))
    parts.append(text(520, 435, "学习样本", 12, 500, T_SECONDARY))
    parts.append(text(520, 475, "12", 36, 900, C_PURPLE_LT, shadow=True))
    parts.append(text(140, H-100, "最近解锁 14:32 · 阈值 0.58 · 模型 SFace", 11, 400, T_HINT))

    # 退出按钮
    parts.append(f'<rect x="{W//2-70}" y="{H-80}" width="140" height="38" rx="19" fill="rgba(255,69,58,0.08)" stroke="rgba(255,69,58,0.3)" filter="url(#dropShadowSm)"/>')
    parts.append(text(W//2, H-55, "退出", 14, 500, C_CORAL_LT, anchor="middle"))

    return render_svg("\n".join(parts), "08_dashboard", W, H)


# ═══════════════════════════════════════════════════════════════
#  主入口
# ═══════════════════════════════════════════════════════════════

if __name__ == "__main__":
    shots = [
        ("1. 识别本人成功",   shot_01_recognize_owner),
        ("2. 识别陌生人",     shot_02_recognize_stranger),
        ("3. 身后入侵守护",   shot_03_guardian_intruder),
        ("4. 离开锁屏休眠",   shot_04_absence),
        ("5. 多帧确认中",     shot_05_recognizing),
        ("6. 设置面板",       shot_06_settings),
        ("7. 注册人脸",       shot_07_enroll),
        ("8. 主面板",         shot_08_dashboard),
    ]
    print("=" * 50)
    print("  FaceGuard · Liquid Glass UI v2 渲染")
    print("  Apple Liquid Glass 2025 · Tim Cook Aesthetic")
    print("=" * 50)
    ok_count = 0
    for name, fn in shots:
        ok = fn()
        mark = "OK" if ok else "FAIL"
        if ok:
            ok_count += 1
        print(f"  [{mark}] {name}")
    print(f"\n  完成: {ok_count}/{len(shots)} 张截图 → {OUT}/")
