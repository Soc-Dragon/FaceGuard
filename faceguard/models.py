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
    # MobileFaceNet - 轻量级识别（更小更快，精度略低）
    "face_recognition_mobilefacenet.onnx": [
        "https://github.com/onnx/models/raw/main/validated/vision/body_analysis/arcface/model/mobilefacenet-9c9db7fc.onnx",
        "https://media.githubusercontent.com/media/onnx/models/main/validated/vision/body_analysis/arcface/model/mobilefacenet-9c9db7fc.onnx",
    ],
    # ArcFace - 高精度识别（模型更大，精度更高）
    "face_recognition_arcface.onnx": [
        "https://github.com/onnx/models/raw/main/validated/vision/body_analysis/arcface/model/resnet50-face-featurizer-v1.onnx",
        "https://media.githubusercontent.com/media/onnx/models/main/validated/vision/body_analysis/arcface/model/resnet50-face-featurizer-v1.onnx",
    ],
}

YUNET_PATH = MODELS_DIR / "face_detection_yunet_2023mar.onnx"
SFACE_PATH = MODELS_DIR / "face_recognition_sface_2021dec.onnx"
MOBILEFACENET_PATH = MODELS_DIR / "face_recognition_mobilefacenet.onnx"
ARCFACE_PATH = MODELS_DIR / "face_recognition_arcface.onnx"

# 可选识别模型：供用户在设置中选择
RECOGNIZER_MODELS = {
    "sface": {
        "path": SFACE_PATH,
        "name": "YuNet + SFace",
        "desc": "默认 · 精度99.5% · 38MB",
        "embedding_size": 128,
        "threshold": 0.55,
        "type": "opencv_sf",  # 使用 cv2.FaceRecognizerSF
    },
    "mobilefacenet": {
        "path": MOBILEFACENET_PATH,
        "name": "MobileFaceNet",
        "desc": "轻量 · 速度快 · 5MB",
        "embedding_size": 192,
        "threshold": 0.45,
        "type": "onnx_dnn",  # 使用 cv2.dnn 读 ONNX
    },
    "arcface": {
        "path": ARCFACE_PATH,
        "name": "ArcFace (ResNet50)",
        "desc": "高精度 · 99.8% · 170MB",
        "embedding_size": 512,
        "threshold": 0.50,
        "type": "onnx_dnn",
    },
}


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
    try:
        if not isinstance(path, Path):
            return None
        parent = path.parent
        if not _ensure_dir(parent):
            return None  # 不再静默改路径
        return open(path, "wb")
    except Exception:
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

        # 防御: 拒绝 HTML 错误页（GitHub LFS pointer、CDN 拦截页等）
        ctype = resp.headers.get("Content-Type", "")
        if "text/html" in ctype or "text/plain" in ctype:
            print(f"[FaceGuard] {dest.name} 下载被拒绝（Content-Type: {ctype}），可能是错误页。", flush=True)
            return False

        total = 0
        try:
            total = int(resp.headers.get("Content-Length", 0))
        except (ValueError, TypeError, AttributeError):
            total = 0

        done = 0
        chunk = 64 * 1024
        interrupted = False
        while True:
            try:
                buf = resp.read(chunk)
            except Exception:
                interrupted = True
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

        # 防御 7: 下载量必须 > 0 且未被中断
        if interrupted or done == 0:
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


def _ensure_model_file(target: Path) -> bool:
    """三级优先级加载单个模型文件：用户目录 → 包内 → 联网下载。返回是否成功。"""
    # 优先级 1: 用户目录已有
    try:
        if target.exists() and target.stat().st_size > 1000:
            return True
    except OSError:
        pass

    # 优先级 2: PyInstaller 包内
    bundled = _bundled_models_dir()
    if bundled is not None:
        b = bundled / target.name
        try:
            if b.exists() and b.stat().st_size > 1000:
                import shutil
                shutil.copy(b, target)
                try:
                    target.chmod(0o644)
                except OSError:
                    pass
                print(f"[FaceGuard] 从安装包复制 {target.name} 到用户目录。", flush=True)
                return True
        except OSError:
            pass

    # 优先级 3: 联网下载
    urls = MODEL_URLS.get(target.name, [])
    if not urls:
        return False
    return _download(urls, target, target.name)


def ensure_models(recognizer_type: str = "sface") -> tuple[Path, Path | None]:
    """确保模型文件就位。

    Args:
        recognizer_type: 用户选择的识别模型 'sface'/'mobilefacenet'/'arcface'

    Returns:
        (yunet_path, recognizer_path) - recognizer_path 可能为 None（加载失败时）
    """
    if not _ensure_dir(MODELS_DIR):
        if not _ensure_dir(APP_DIR):
            print("[FaceGuard] 无法创建数据目录，模型加载将跳过。", flush=True)
            return YUNET_PATH, None

    # YuNet 检测器是必须的
    yunet_ok = _ensure_model_file(YUNET_PATH)
    if not yunet_ok:
        print("[FaceGuard] YuNet 检测模型加载失败，无法进行人脸检测。", flush=True)
        return YUNET_PATH, None

    # 根据用户选择加载对应识别模型
    rec_info = RECOGNIZER_MODELS.get(recognizer_type, RECOGNIZER_MODELS["sface"])
    rec_path = rec_info["path"]
    rec_ok = _ensure_model_file(rec_path)

    # 如果用户选的模型加载失败，自动回退到 SFace（默认打包的）
    if not rec_ok and recognizer_type != "sface":
        print(f"[FaceGuard] {rec_info['name']} 加载失败，回退到默认 SFace。", flush=True)
        rec_info = RECOGNIZER_MODELS["sface"]
        rec_path = rec_info["path"]
        rec_ok = _ensure_model_file(rec_path)

    if not rec_ok:
        print(f"[FaceGuard] 识别模型加载失败，将以降级模式运行。", flush=True)
        return YUNET_PATH, None

    print(f"[FaceGuard] 识别模型: {rec_info['name']} ({rec_info['desc']})", flush=True)
    return YUNET_PATH, rec_path
