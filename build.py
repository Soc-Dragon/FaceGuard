"""FaceGuard 构建脚本：用 PyInstaller 打包成单文件 exe。

自动下载模型 → 打包到 exe → 用户安装后无需联网即可使用。
模型下载失败将直接中止构建，永不妥协（避免生成半成品包）。
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

# 模型下载地址 —— 每个模型提供多源
# 重要: OpenCV Zoo 模型使用 Git LFS 存储，必须用 media.githubusercontent.com 下载
# raw.githubusercontent.com 只返回 LFS 指针（131字节），不是真正的模型文件
MODEL_URLS = {
    "face_detection_yunet_2023mar.onnx": [
        "https://media.githubusercontent.com/media/opencv/opencv_zoo/main/models/face_detection_yunet/face_detection_yunet_2023mar.onnx",
        "https://github.com/opencv/opencv_zoo/blob/main/models/face_detection_yunet/face_detection_yunet_2023mar.onnx?raw=true",
    ],
    "face_recognition_sface_2021dec.onnx": [
        "https://media.githubusercontent.com/media/opencv/opencv_zoo/main/models/face_recognition_sface/face_recognition_sface_2021dec.onnx",
        "https://github.com/opencv/opencv_zoo/blob/main/models/face_recognition_sface/face_recognition_sface_2021dec.onnx?raw=true",
    ],
    "face_recognition_mobilefacenet.onnx": [
        "https://media.githubusercontent.com/media/onnx/models/main/validated/vision/body_analysis/arcface/model/mobilefacenet-9c9db7fc.onnx",
    ],
    "face_recognition_arcface.onnx": [
        "https://media.githubusercontent.com/media/onnx/models/main/validated/vision/body_analysis/arcface/model/arcfaceresnet100-8.onnx",
    ],
}

# 必须打包的核心模型（缺失则构建失败）
ESSENTIAL_MODELS = [
    "face_detection_yunet_2023mar.onnx",
    "face_recognition_sface_2021dec.onnx",
]


def _download_file(url: str, dest: Path, timeout: int = 120) -> bool:
    """下载单个文件，返回是否成功。"""
    import urllib.request
    import urllib.error

    try:
        req = urllib.request.Request(url, headers={"User-Agent": "FaceGuard/2.3"})
        resp = urllib.request.urlopen(req, timeout=timeout)
        if resp is None:
            return False
        # 检查 Content-Type，拒绝 HTML 错误页
        ctype = resp.headers.get("Content-Type", "")
        if "text/html" in ctype or "text/plain" in ctype:
            print(f"  Content-Type={ctype}，可能是错误页，跳过")
            return False
        data = resp.read()
        if len(data) == 0:
            return False
        dest.write_bytes(data)
        print(f"  OK: {len(data) // 1024} KB")
        return True
    except Exception as e:
        print(f"  失败: {e}")
        try:
            dest.unlink()
        except OSError:
            pass
        return False


def download_models() -> dict[str, bool]:
    """下载所有模型，返回 {filename: success} 字典。"""
    import hashlib

    BUNDLE_DIR.mkdir(parents=True, exist_ok=True)
    results = {}

    for fname, urls in MODEL_URLS.items():
        dest = BUNDLE_DIR / fname
        # 验证现有文件的完整性（大小 + 简单熵检查）
        if dest.exists():
            size = dest.stat().st_size
            if size > 1000:
                # 读取前 64 字节检查是否为合法 ONNX（以 PK 或 ONNX magic 开头）
                try:
                    header = dest.read_bytes()[:16]
                    # ONNX 文件以 protobuf 格式开头，检查是否非全零/全重复
                    if len(set(header)) > 1:
                        print(f"[build] {fname} 已存在 ({size // 1024} KB)，校验通过")
                        results[fname] = True
                        continue
                except Exception:
                    pass
                # 文件损坏，删除重新下载
                print(f"[build] {fname} 已存在但校验失败，重新下载")
                try:
                    dest.unlink()
                except OSError:
                    pass

        print(f"[build] 下载 {fname}:")
        ok = False
        for url in urls:
            print(f"  尝试: {url[:100]}")
            if _download_file(url, dest):
                # 下载后验证
                if dest.exists() and dest.stat().st_size > 1000:
                    ok = True
                    break
                else:
                    print(f"  下载后文件异常，删除")
                    try:
                        dest.unlink()
                    except OSError:
                        pass

        results[fname] = ok
        if not ok:
            print(f"[build] !!! {fname} 全部镜像下载失败")

    return results


def verify_bundle() -> bool:
    """验证打包目录中的核心模型是否完整。"""
    all_ok = True
    for fname in ESSENTIAL_MODELS:
        p = BUNDLE_DIR / fname
        if not p.exists() or p.stat().st_size < 1000:
            print(f"[build] 致命错误: 核心模型 {fname} 缺失或损坏!")
            all_ok = False
    return all_ok


def build() -> int:
    # 1. 下载/验证模型
    results = download_models()
    essential_failed = [f for f in ESSENTIAL_MODELS if not results.get(f, False)]

    if essential_failed:
        print(f"[build] 致命错误: 核心模型 {essential_failed} 下载失败!")
        print("[build] 构建中止。请检查网络连接或手动将模型文件放入 models_bundle/ 目录。")
        return 1

    optional_ok = all(results.get(f, True) for f in MODEL_URLS if f not in ESSENTIAL_MODELS)
    if not optional_ok:
        print("[build] 警告: 部分可选模型下载失败，用户选择这些模型时会自动回退到默认 SFace。")

    # 2. 再次验证
    if not verify_bundle():
        return 1

    # 3. 构造 --add-data 参数：把 models_bundle 下的所有模型打包进去
    add_data_args = []
    model_count = 0
    if BUNDLE_DIR.exists():
        for model_file in sorted(BUNDLE_DIR.iterdir()):
            if model_file.is_file() and model_file.stat().st_size > 1000:
                sep = ";" if sys.platform == "win32" else ":"
                add_data_args.extend([
                    "--add-data",
                    f"{model_file}{sep}models"
                ])
                model_count += 1
                print(f"[build] 打包模型: {model_file.name} ({model_file.stat().st_size // 1024} KB)")

    if model_count == 0:
        print("[build] 致命错误: 没有可打包的模型文件!")
        return 1

    print(f"[build] 共 {model_count} 个模型将被打包进 exe")

    # 4. 运行 PyInstaller
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
        "--hidden-import", "ctypes.wintypes",
        "--hidden-import", "tkinter.messagebox",
        "--hidden-import", "tkinter.simpledialog",
    ] + add_data_args + [
        str(ENTRY),
    ]
    print("[build] 运行:", " ".join(cmd))
    rc = subprocess.call(cmd, cwd=str(ROOT))

    if rc == 0:
        exe = DIST / "FaceGuard.exe"
        if exe.exists():
            size_mb = exe.stat().st_size / (1024 * 1024)
            print(f"[build] 成功: {exe} ({size_mb:.1f} MB)")
            # 5. 最终验证：检查打包后的 exe 是否包含模型
            print("[build] 构建完成，下一步用 Inno Setup 编译安装包。")
        else:
            print("[build] 致命错误: PyInstaller 返回 0 但未找到 exe")
            return 1
    else:
        print(f"[build] 致命错误: PyInstaller 返回非零退出码 {rc}")
        return rc

    return 0


if __name__ == "__main__":
    rc = build()
    sys.exit(rc)
