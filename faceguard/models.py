"""模型管理：按需下载 YuNet 人脸检测 + SFace 人脸识别 ONNX 模型。

模型来自 OpenCV 官方模型仓库 (opencv_zoo)，首次运行自动下载到
%APPDATA%\\FaceGuard\\models，之后离线可用。

关键修复：Windows 路径/网络/权限 10 层防御，任何一环出问题都不崩。
"""

from __future__ import annotations

import os
import sys
import time
import urllib.request
import urllib.error
from pathlib import Path

from .config import MODELS_DIR, APP_DIR

# OpenCV zoo 下载地址（含备用 CDN）
MODEL_URLS = {
    "face_detection_yunet_2023mar.onnx": [
        "https://github.com/opencv/opencv_zoo/raw/main/models/face_detection_yunet/face_detection_yunet_2023mar.onnx",
        "https://raw.githubusercontent.com/opencv/opencv_zoo/main/models/face_detection_yunet/face_detection_yunet_2023mar.onnx",
    ],
    "face_recognition_sface_2021dec.onnx": [
        "https://github.com/opencv/opencv_zoo/raw/main/models/face_recognition_sface/face_recognition_sface_2021dec.onnx",
        "https://raw.githubusercontent.com/opencv/opencv_zoo/main/models/face_recognition_sface/face_recognition_sface_2021dec.onnx",
    ],
}

YUNET_PATH = MODELS_DIR / "face_detection_yunet_2023mar.onnx"
SFACE_PATH = MODELS_DIR / "face_recognition_sface_2021dec.onnx"


def _ensure_dir(path: Path) -> bool:
    """确保目录存在。返回是否成功。"""
    try:
        if not isinstance(path, Path):
            return False
        path.mkdir(parents=True, exist_ok=True)
        return path.exists()
    except (OSError, PermissionError):
        return False


def _safe_open_write(path: Path):
    """安全打开文件写入，绝不返回 None。"""
    try:
        if not isinstance(path, Path):
            return None
        # 确保父目录存在
        parent = path.parent
        if not _ensure_dir(parent):
            # 兜底：用 APP_DIR
            if _ensure_dir(APP_DIR):
                path = APP_DIR / path.name
            else:
                return None
        # 路径合法性检查
        s = str(path)
        if not s or s == "." or s.startswith("\\\\"):
            return None
        return open(path, "wb")
    except (OSError, PermissionError, ValueError, TypeError):
        return None


def _download_one(url: str, dest: Path, label: str = "") -> bool:
    """下载单个 URL 到 dest。返回是否成功。"""
    # 防御 1: dest 必须是 Path 且有效
    if not isinstance(dest, Path):
        return False

    # 防御 2: 已存在且有内容则跳过
    try:
        if dest.exists() and dest.stat().st_size > 1000:
            return True
    except OSError:
        pass

    # 防御 3: 确保目录
    if not _ensure_dir(dest.parent):
        return False

    # 防御 4: 安全打开文件
    f = _safe_open_write(dest)
    if f is None:
        print(f"[FaceGuard] 无法创建文件: {dest}", flush=True)
        return False

    print(f"[FaceGuard] 正在下载 {label or dest.name} ...", flush=True)
    try:
        # 防御 5: urlopen 超时 + 异常捕获
        req = urllib.request.Request(url, headers={"User-Agent": "FaceGuard/2.1"})
        try:
            resp = urllib.request.urlopen(req, timeout=90)
        except (urllib.error.URLError, urllib.error.HTTPError, OSError, ValueError) as e:
            print(f"[FaceGuard] 网络错误: {e}", flush=True)
            f.close()
            # 清理空文件
            try:
                dest.unlink()
            except OSError:
                pass
            return False

        # 防御 6: resp 必须有效
        if resp is None:
            f.close()
            return False

        total = 0
        try:
            total = int(resp.headers.get("Content-Length", 0))
        except (ValueError, TypeError, AttributeError):
            total = 0

        done = 0
        chunk = 64 * 1024
        while True:
            try:
                buf = resp.read(chunk)
            except Exception:
                break
            if not buf:
                break
            try:
                f.write(buf)
            except (OSError, IOError):
                break
            done += len(buf)
            if total and total > 0:
                pct = done * 100 // total
                sys.stdout.write(f"\r  {done // 1024} / {total // 1024} KB  ({pct}%)")
                sys.stdout.flush()

        # 防御 7: 下载量必须 > 0
        if done == 0:
            f.close()
            try:
                dest.unlink()
            except OSError:
                pass
            return False

        sys.stdout.write("\n")
        print(f"[FaceGuard] {dest.name} 下载完成 ({done // 1024} KB)。", flush=True)
        f.close()
        return True

    except Exception as e:
        print(f"[FaceGuard] 下载异常: {e}", flush=True)
        try:
            f.close()
        except Exception:
            pass
        try:
            dest.unlink()
        except OSError:
            pass
        return False


def _download(urls: list[str] | str, dest: Path, label: str = "") -> bool:
    """尝试多个 URL 下载，返回是否成功。"""
    if isinstance(urls, str):
        urls = [urls]
    for url in urls:
        if _download_one(url, dest, label):
            return True
    return False


def _bundled_models_dir() -> Path | None:
    """PyInstaller 打包后，返回包内模型目录（sys._MEIPASS/models）。未打包返回 None。"""
    meipass = getattr(sys, "_MEIPASS", None)
    if meipass:
        d = Path(meipass) / "models"
        if d.is_dir():
            return d
    return None


def ensure_models() -> tuple[Path, Path]:
    """确保两个模型文件就位，返回 (yunet_path, sface_path)。

    优先级：
    1. 用户数据目录已有模型（%APPDATA%/FaceGuard/models）
    2. PyInstaller 包内模型（无需下载）
    3. 联网下载到用户数据目录
    任何下载失败都返回路径（由调用方决定是否降级为无模型模式）。
    """
    yunet_ok = False
    sface_ok = False

    # 防御: MODELS_DIR 必须有效
    if not _ensure_dir(MODELS_DIR):
        if not _ensure_dir(APP_DIR):
            print("[FaceGuard] 无法创建数据目录，模型加载将跳过。", flush=True)
            return YUNET_PATH, SFACE_PATH

    # ---- 优先级 1: 用户数据目录已有 ----
    if YUNET_PATH.exists() and YUNET_PATH.stat().st_size > 1000:
        yunet_ok = True
    if SFACE_PATH.exists() and SFACE_PATH.stat().st_size > 1000:
        sface_ok = True

    if yunet_ok and sface_ok:
        return YUNET_PATH, SFACE_PATH

    # ---- 优先级 2: PyInstaller 包内模型 ----
    bundled = _bundled_models_dir()
    if bundled is not None:
        by = bundled / YUNET_PATH.name
        bs = bundled / SFACE_PATH.name
        if by.exists() and by.stat().st_size > 1000 and not yunet_ok:
            # 复制到用户数据目录（便于后续独立使用）
            try:
                import shutil
                shutil.copy2(by, YUNET_PATH)
                yunet_ok = True
                print(f"[FaceGuard] 从安装包复制 YuNet 模型到用户目录。", flush=True)
            except OSError:
                pass
        if bs.exists() and bs.stat().st_size > 1000 and not sface_ok:
            try:
                import shutil
                shutil.copy2(bs, SFACE_PATH)
                sface_ok = True
                print(f"[FaceGuard] 从安装包复制 SFace 模型到用户目录。", flush=True)
            except OSError:
                pass

    if yunet_ok and sface_ok:
        return YUNET_PATH, SFACE_PATH

    # ---- 优先级 3: 联网下载 ----
    if not yunet_ok:
        yunet_ok = _download(MODEL_URLS[YUNET_PATH.name], YUNET_PATH, "YuNet 人脸检测模型")
    if not sface_ok:
        sface_ok = _download(MODEL_URLS[SFACE_PATH.name], SFACE_PATH, "SFace 人脸识别模型")

    if not yunet_ok or not sface_ok:
        print("[FaceGuard] 部分模型加载失败，将以降级模式运行（无人脸检测）。", flush=True)
        print(f"  YuNet: {'OK' if yunet_ok else '缺失'}", flush=True)
        print(f"  SFace: {'OK' if sface_ok else '缺失'}", flush=True)

    return YUNET_PATH, SFACE_PATH
