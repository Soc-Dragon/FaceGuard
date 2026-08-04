"""模型管理：按需下载 YuNet 人脸检测 + SFace 人脸识别 ONNX 模型。

模型来自 OpenCV 官方模型仓库 (opencv_zoo)，首次运行自动下载到
%APPDATA%\\FaceGuard\\models，之后离线可用。

三级加载策略：用户目录 → 安装包内嵌 → 联网下载（含中国镜像）
"""

from __future__ import annotations

import os
import sys
import time
import urllib.request
import urllib.error
from pathlib import Path

from .config import MODELS_DIR, APP_DIR

# 模型下载地址 —— 每个模型提供多源
# 重要: OpenCV Zoo 模型使用 Git LFS 存储，必须用 media.githubusercontent.com 下载
# raw.githubusercontent.com 只返回 LFS 指针（131字节），不是真正的模型文件
MODEL_URLS = {
    "face_detection_yunet_2023mar.onnx": [
        # GitHub LFS 正确下载地址（必须用这个）
        "https://media.githubusercontent.com/media/opencv/opencv_zoo/main/models/face_detection_yunet/face_detection_yunet_2023mar.onnx",
        # GitHub blob 页面（备用）
        "https://github.com/opencv/opencv_zoo/blob/main/models/face_detection_yunet/face_detection_yunet_2023mar.onnx?raw=true",
    ],
    "face_recognition_sface_2021dec.onnx": [
        "https://media.githubusercontent.com/media/opencv/opencv_zoo/main/models/face_recognition_sface/face_recognition_sface_2021dec.onnx",
        "https://github.com/opencv/opencv_zoo/blob/main/models/face_recognition_sface/face_recognition_sface_2021dec.onnx?raw=true",
    ],
    "face_recognition_mobilefacenet.onnx": [
        # 可选模型：第三方来源（如果下载失败会自动回退到默认 SFace）
        "https://media.githubusercontent.com/media/onnx/models/main/validated/vision/body_analysis/arcface/model/mobilefacenet-9c9db7fc.onnx",
    ],
    "face_recognition_arcface.onnx": [
        # 可选模型：ArcFace ResNet100 (250MB)
        "https://media.githubusercontent.com/media/onnx/models/main/validated/vision/body_analysis/arcface/model/arcfaceresnet100-8.onnx",
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
        "type": "opencv_sf",
    },
    "mobilefacenet": {
        "path": MOBILEFACENET_PATH,
        "name": "MobileFaceNet",
        "desc": "轻量 · 速度快 · 5MB",
        "embedding_size": 192,
        "threshold": 0.45,
        "type": "onnx_dnn",
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
            return None
        return open(path, "wb")
    except Exception:
        return None


def _download_one(url: str, dest: Path, label: str = "") -> bool:
    if not isinstance(dest, Path):
        return False

    try:
        if dest.exists() and dest.stat().st_size > 1000:
            return True
    except OSError:
        pass

    if not _ensure_dir(dest.parent):
        return False

    f = _safe_open_write(dest)
    if f is None:
        print(f"[FaceGuard] 无法创建文件: {dest}", flush=True)
        return False

    print(f"[FaceGuard] 正在下载 {label or dest.name} ...", flush=True)
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "FaceGuard/2.3"})
        try:
            resp = urllib.request.urlopen(req, timeout=90)
        except (urllib.error.URLError, urllib.error.HTTPError, OSError, ValueError) as e:
            print(f"[FaceGuard] 网络错误: {e}", flush=True)
            f.close()
            try:
                dest.unlink()
            except OSError:
                pass
            return False

        if resp is None:
            f.close()
            return False

        ctype = resp.headers.get("Content-Type", "")
        if "text/html" in ctype or "text/plain" in ctype:
            print(f"[FaceGuard] {dest.name} 下载被拒绝（Content-Type: {ctype}）", flush=True)
            f.close()
            try:
                dest.unlink()
            except OSError:
                pass
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
                interrupted = True
                break
            done += len(buf)
            if total and total > 0:
                pct = done * 100 // total
                sys.stdout.write(f"\r  {done // 1024} / {total // 1024} KB  ({pct}%)")
                sys.stdout.flush()

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
    if isinstance(urls, str):
        urls = [urls]
    for url in urls:
        if _download_one(url, dest, label):
            return True
    return False


def _bundled_models_dir() -> Path | None:
    """查找 PyInstaller 打包后的内嵌模型目录。

    按优先级尝试多个可能的位置：
    1. sys._MEIPASS/models  (PyInstaller --onefile 标准位置)
    2. 可执行文件同级目录/models  (便携模式或解压后)
    3. APP_DIR/models_bundle  (用户手动放置)
    """
    candidates = []

    # 优先级 1: PyInstaller _MEIPASS
    meipass = getattr(sys, "_MEIPASS", None)
    if meipass:
        candidates.append(Path(meipass) / "models")

    # 优先级 2: 可执行文件同级目录 (便携部署)
    exe_dir = Path(sys.executable).parent
    candidates.append(exe_dir / "models")

    # 优先级 3: 应用目录下的 models_bundle
    candidates.append(APP_DIR / "models_bundle")

    for d in candidates:
        if d.is_dir():
            # 验证目录内至少有一个 ONNX 文件
            try:
                onnx_files = list(d.glob("*.onnx"))
                if onnx_files:
                    print(f"[FaceGuard] 找到内嵌模型目录: {d} ({len(onnx_files)} 个文件)", flush=True)
                    return d
            except OSError:
                continue

    return None


def _verify_model_file(path: Path) -> bool:
    """验证模型文件是否有效（大小 + 内容检查）。"""
    try:
        if not path.exists():
            return False
        size = path.stat().st_size
        if size < 1000:
            return False
        # 读取前 16 字节，检查是否为合法二进制（非全零/全空格/HTML）
        header = path.read_bytes()[:16]
        if len(set(header)) <= 1:
            return False  # 全零或全重复
        # 检查是否以 <!DOCTYPE 或 <html 开头（HTML 错误页）
        try:
            text = header.decode("ascii", errors="ignore").lower()
            if "<!doctype" in text or "<html" in text:
                return False
        except Exception:
            pass
        return True
    except (OSError, PermissionError):
        return False


def _copy_model(src: Path, dst: Path) -> bool:
    """复制模型文件，带验证。"""
    import shutil
    try:
        if not src.exists():
            return False
        # 确保目标目录存在
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)
        # 验证复制结果
        if not _verify_model_file(dst):
            print(f"[FaceGuard] 模型复制后校验失败: {dst}", flush=True)
            try:
                dst.unlink()
            except OSError:
                pass
            return False
        try:
            dst.chmod(0o644)
        except OSError:
            pass
        return True
    except Exception as e:
        print(f"[FaceGuard] 模型复制失败: {e}", flush=True)
        try:
            if dst.exists():
                dst.unlink()
        except OSError:
            pass
        return False


def _ensure_model_file(target: Path) -> bool:
    """三级加载单个模型文件：用户目录 → 包内 → 联网下载。"""
    # 优先级 1: 用户目录已有且有效
    if _verify_model_file(target):
        return True

    # 优先级 2: 从安装包内嵌复制
    bundled = _bundled_models_dir()
    if bundled is not None:
        b = bundled / target.name
        if _verify_model_file(b):
            if _copy_model(b, target):
                print(f"[FaceGuard] 从安装包复制 {target.name} 到用户目录。", flush=True)
                return True
            else:
                print(f"[FaceGuard] 从安装包复制 {target.name} 失败，尝试下载。", flush=True)

    # 优先级 3: 联网下载（多镜像）
    urls = MODEL_URLS.get(target.name, [])
    if not urls:
        return False

    # 先尝试所有镜像
    for url in urls:
        if _download_one(url, target, target.name):
            if _verify_model_file(target):
                return True
            else:
                print(f"[FaceGuard] {target.name} 下载后校验失败，删除重下。", flush=True)
                try:
                    target.unlink()
                except OSError:
                    pass

    return False


def ensure_models(recognizer_type: str = "sface") -> tuple[Path, Path | None]:
    """确保模型文件就位。

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
        print("[FaceGuard] 请检查网络连接，或手动将 face_detection_yunet_2023mar.onnx 放入:", flush=True)
        print(f"  {MODELS_DIR}", flush=True)
        return YUNET_PATH, None

    # 根据用户选择加载对应识别模型
    rec_info = RECOGNIZER_MODELS.get(recognizer_type, RECOGNIZER_MODELS["sface"])
    rec_path = rec_info["path"]
    rec_ok = _ensure_model_file(rec_path)

    # 如果用户选的模型加载失败，自动回退到 SFace
    if not rec_ok and recognizer_type != "sface":
        print(f"[FaceGuard] {rec_info['name']} 加载失败，回退到默认 SFace。", flush=True)
        rec_info = RECOGNIZER_MODELS["sface"]
        rec_path = rec_info["path"]
        rec_ok = _ensure_model_file(rec_path)

    if not rec_ok:
        print(f"[FaceGuard] 识别模型加载失败，将以降级模式运行。", flush=True)
        print("[FaceGuard] 请检查网络连接，或手动将 face_recognition_sface_2021dec.onnx 放入:", flush=True)
        print(f"  {MODELS_DIR}", flush=True)
        return YUNET_PATH, None

    print(f"[FaceGuard] 识别模型: {rec_info['name']} ({rec_info['desc']})", flush=True)
    return YUNET_PATH, rec_path
