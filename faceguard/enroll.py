"""人脸注册向导：首次使用时采集本人人脸特征。

提供命令行交互式注册（打包后由主程序 --enroll 调用）。
"""

from __future__ import annotations

import logging
import time

import cv2

from .camera import Camera
from .recognizer import Recognizer

log = logging.getLogger("faceguard.enroll")


def enroll_interactive(cfg: dict, name: str | None = None) -> bool:
    """交互式采集：捕获多张人脸，提取特征入库。"""
    rcfg = cfg.get("recognizer", {})
    cam = Camera(rcfg.get("camera_index", 0),
                 rcfg.get("frame_width", 640),
                 rcfg.get("frame_height", 480),
                 rcfg.get("fps", 15))
    if not cam.open():
        print("[FaceGuard] 无法打开摄像头，注册失败。")
        return False

    rec = Recognizer(cfg)
    if not rec.init_models():
        print("[FaceGuard] 模型加载失败。")
        cam.release()
        return False

    if not name:
        name = input("请输入你的名字（用于人脸标签）: ").strip() or "owner"

    print(f"[FaceGuard] 开始为 [{name}] 采集人脸，请正对摄像头...")
    print("将采集 8 张不同角度，请缓慢转头。按 ESC 取消。")

    collected = 0
    target = 8
    last_capture = 0.0
    interval = 0.6

    while collected < target:
        ok, frame = cam.read()
        if not ok:
            time.sleep(0.05)
            continue
        faces = rec.detect(frame)
        display = frame.copy()
        if faces:
            f = max(faces, key=lambda x: x.area_ratio)
            cv2.rectangle(display, (f.x, f.y), (f.x + f.w, f.y + f.h),
                          (0, 255, 0), 2)
        cv2.putText(display, f"采集 {collected}/{target}  正对摄像头",
                    (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 255), 2)
        cv2.imshow("FaceGuard Enroll", display)
        key = cv2.waitKey(1) & 0xFF
        if key == 27:
            break
        if faces and (time.time() - last_capture) > interval:
            f = max(faces, key=lambda x: x.area_ratio)
            emb = rec.extract_embedding(frame, f)
            if emb is not None:
                rec.enroll(f"{name}_{collected}", emb)
                collected += 1
                last_capture = time.time()
                print(f"  已采集 {collected}/{target}")

    cam.release()
    cv2.destroyAllWindows()

    if collected >= 3:
        print(f"[FaceGuard] 注册完成！共采集 {collected} 张。")
        return True
    print("[FaceGuard] 采集数量不足，注册失败。")
    return False
