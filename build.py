"""FaceGuard 构建脚本：用 PyInstaller 打包成单文件 exe。

本地构建：python build.py
GitHub Actions 也会调用本脚本。
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

# Windows 控制台默认 cp1252，输出中文会 UnicodeEncodeError，强制 UTF-8
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

ROOT = Path(__file__).parent
ENTRY = ROOT / "faceguard" / "__main__.py"
DIST = ROOT / "dist"
BUILD = ROOT / "build"


def build() -> int:
    cmd = [
        sys.executable, "-m", "PyInstaller",
        "--noconfirm",
        "--clean",
        "--onefile",
        "--windowed",                       # 无控制台窗口（GUI/守护）
        "--name", "FaceGuard",
        "--collect-all", "cv2",             # OpenCV 数据文件
        # 图标（如有）
        # "--icon", str(ROOT / "release" / "faceguard.ico"),
        str(ENTRY),
    ]
    print("[build] 运行:", " ".join(cmd))
    return subprocess.call(cmd, cwd=str(ROOT))


if __name__ == "__main__":
    rc = build()
    if rc == 0:
        exe = DIST / "FaceGuard.exe"
        if exe.exists():
            print(f"[build] 成功: {exe} ({exe.stat().st_size // 1024} KB)")
        else:
            print("[build] PyInstaller 返回 0 但未找到 exe")
    sys.exit(rc)
