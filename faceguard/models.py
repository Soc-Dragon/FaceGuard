"""模型管理：按需下载 YuNet 人脸检测 + SFace 人脸识别 ONNX 模型。

模型来自 OpenCV 官方模型仓库 (opencv_zoo)，首次运行自动下载到
%APPDATA%\\FaceGuard\\models，之后离线可用。
"""

from __future__ import annotations

import sys
import urllib.request
from pathlib import Path

from .config import MODELS_DIR

# OpenCV zoo 稳定下载地址
MODEL_URLS = {
    # YuNet 人脸检测器，速度快、精度高
    "face_detection_yunet_2023mar.onnx": (
        "https://github.com/opencv/opencv_zoo/raw/main/models/"
        "face_detection_yunet/face_detection_yunet_2023mar.onnx"
    ),
    # SFace 人脸识别器，LFW 99.55%
    "face_recognition_sface_2021dec.onnx": (
        "https://github.com/opencv/opencv_zoo/raw/main/models/"
        "face_recognition_sface/face_recognition_sface_2021dec.onnx"
    ),
}

YUNET_PATH = MODELS_DIR / "face_detection_yunet_2023mar.onnx"
SFACE_PATH = MODELS_DIR / "face_recognition_sface_2021dec.onnx"


def _download(url: str, dest: Path, label: str = "") -> None:
    """带进度提示的下载。"""
    if dest.exists() and dest.stat().st_size > 0:
        return
    dest.parent.mkdir(parents=True, exist_ok=True)
    print(f"[FaceGuard] 正在下载 {label or dest.name} ...", flush=True)
    req = urllib.request.Request(url, headers={"User-Agent": "FaceGuard/2.1"})
    with urllib.request.urlopen(req, timeout=60) as resp, dest.open("wb") as f:
        total = int(resp.headers.get("Content-Length", 0))
        done = 0
        chunk = 64 * 1024
        while True:
            buf = resp.read(chunk)
            if not buf:
                break
            f.write(buf)
            done += len(buf)
            if total:
                pct = done * 100 // total
                sys.stdout.write(f"\r  {done//1024} / {total//1024} KB  ({pct}%)")
                sys.stdout.flush()
    sys.stdout.write("\n")
    print(f"[FaceGuard] {dest.name} 下载完成。", flush=True)


def ensure_models() -> tuple[Path, Path]:
    """确保两个模型文件就位，返回 (yunet_path, sface_path)。"""
    _download(MODEL_URLS[YUNET_PATH.name], YUNET_PATH, "YuNet 人脸检测模型")
    _download(MODEL_URLS[SFACE_PATH.name], SFACE_PATH, "SFace 人脸识别模型")
    return YUNET_PATH, SFACE_PATH
