"""FaceGuard 构建脚本：用 PyInstaller 打包成单文件 exe。

自动下载模型 → 打包到 exe → 用户安装后无需联网即可使用。
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
ENTRY = ROOT / "run.py"
DIST = ROOT / "dist"
BUILD = ROOT / "build"
BUNDLE_DIR = ROOT / "models_bundle"

# 模型下载地址（与 models.py 保持一致）
MODEL_URLS = {
    "face_detection_yunet_2023mar.onnx": [
        "https://github.com/opencv/opencv_zoo/raw/main/models/face_detection_yunet/face_detection_yunet_2023mar.onnx",
        "https://raw.githubusercontent.com/opencv/opencv_zoo/main/models/face_detection_yunet/face_detection_yunet_2023mar.onnx",
    ],
    "face_recognition_sface_2021dec.onnx": [
        "https://github.com/opencv/opencv_zoo/raw/main/models/face_recognition_sface/face_recognition_sface_2021dec.onnx",
        "https://raw.githubusercontent.com/opencv/opencv_zoo/main/models/face_recognition_sface/face_recognition_sface_2021dec.onnx",
    ],
    "face_recognition_mobilefacenet.onnx": [
        "https://github.com/onnx/models/raw/main/validated/vision/body_analysis/arcface/model/mobilefacenet-9c9db7fc.onnx",
        "https://raw.githubusercontent.com/onnx/models/main/validated/vision/body_analysis/arcface/model/mobilefacenet-9c9db7fc.onnx",
    ],
    "face_recognition_arcface.onnx": [
        "https://github.com/onnx/models/raw/main/validated/vision/body_analysis/arcface/model/resnet50-face-featurizer-v1.onnx",
        "https://raw.githubusercontent.com/onnx/models/main/validated/vision/body_analysis/arcface/model/resnet50-face-featurizer-v1.onnx",
    ],
}


def download_models() -> bool:
    """下载模型到 models_bundle/，返回是否全部成功。"""
    import urllib.request
    import urllib.error

    BUNDLE_DIR.mkdir(parents=True, exist_ok=True)
    all_ok = True

    for fname, urls in MODEL_URLS.items():
        dest = BUNDLE_DIR / fname
        if dest.exists() and dest.stat().st_size > 1000:
            print(f"[build] {fname} 已存在，跳过下载")
            continue

        ok = False
        for url in urls:
            print(f"[build] 下载 {fname} from {url[:80]}...")
            try:
                req = urllib.request.Request(url, headers={"User-Agent": "FaceGuard/2.1"})
                resp = urllib.request.urlopen(req, timeout=120)
                data = resp.read()
                if len(data) > 0:
                    dest.write_bytes(data)
                    print(f"[build] {fname} 下载成功 ({len(data) // 1024} KB)")
                    ok = True
                    break
            except Exception as e:
                print(f"[build] 下载失败: {e}")
                try:
                    dest.unlink()
                except OSError:
                    pass

        if not ok:
            print(f"[build] !!! {fname} 全部下载失败")
            all_ok = False

    return all_ok


def build() -> int:
    # 先下载模型
    models_ok = download_models()
    if not models_ok:
        print("[build] 警告: 部分模型下载失败，打包的 exe 将需要首次联网下载模型。")
        print("[build] 继续打包...")

    # 构造 --add-data 参数：把 models_bundle 下的所有模型打包进去
    add_data_args = []
    if BUNDLE_DIR.exists():
        for model_file in BUNDLE_DIR.iterdir():
            if model_file.is_file():
                # Windows 用 ; 分隔源和目标，Linux 用 :
                sep = ";" if sys.platform == "win32" else ":"
                add_data_args.extend([
                    "--add-data",
                    f"{model_file}{sep}models"
                ])
                print(f"[build] 打包模型: {model_file.name}")

    cmd = [
        sys.executable, "-m", "PyInstaller",
        "--noconfirm",
        "--clean",
        "--onefile",
        "--windowed",
        "--name", "FaceGuard",
        "--collect-all", "cv2",
        "--collect-all", "numpy",
        "--collect-all", "PIL",
        "--hidden-import", "PIL.ImageTk",
    ] + add_data_args + [
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
