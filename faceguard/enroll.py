"""人脸注册向导：首次使用时采集本人人脸特征。

提供交互式注册（打包后由主程序 --enroll 调用）。
支持无控制台模式（--windowed 打包）：用 tkinter 对话框替代 input/print。
"""

from __future__ import annotations

import logging
import time

import cv2

from .camera import Camera
from .recognizer import Recognizer

log = logging.getLogger("faceguard.enroll")


def _ask_name_dialog() -> str:
    """tkinter 对话框请求输入名字（--windowed 打包时无 stdin，不能用 input）。"""
    try:
        import tkinter as tk
        from tkinter import simpledialog
        root = tk.Tk()
        root.withdraw()
        root.attributes("-topmost", True)
        name = simpledialog.askstring(
            "FaceGuard · 注册人脸",
            "请输入你的名字（用于人脸标签）：",
            initialvalue="owner",
            parent=root,
        )
        root.destroy()
        return (name or "").strip() or "owner"
    except Exception:
        # tkinter 不可用时回退（有控制台的情况）
        try:
            return input("请输入你的名字（用于人脸标签）: ").strip() or "owner"
        except (EOFError, OSError, AttributeError):
            return "owner"


def _alert(title: str, message: str, icon: str = "warning") -> None:
    """无控制台模式下弹出对话框。"""
    try:
        import tkinter as tk
        from tkinter import messagebox
        root = tk.Tk()
        root.withdraw()
        root.attributes("-topmost", True)
        if icon == "error":
            messagebox.showerror(title, message, parent=root)
        elif icon == "info":
            messagebox.showinfo(title, message, parent=root)
        else:
            messagebox.showwarning(title, message, parent=root)
        root.destroy()
    except Exception as e:
        # --windowed 模式下 sys.stdout 可能为 None，用 log 替代 print
        log.error("%s: %s (%s)", title, message, e)


def enroll_interactive(cfg: dict, name: str | None = None) -> bool:
    """交互式采集：捕获多张人脸，提取特征入库。"""
    rcfg = cfg.get("recognizer", {})
    cam = Camera(rcfg.get("camera_index", 0),
                 rcfg.get("frame_width", 640),
                 rcfg.get("frame_height", 480),
                 rcfg.get("fps", 15))
    if not cam.open():
        _alert("FaceGuard · 摄像头错误",
               "无法打开摄像头，注册失败。\n请检查摄像头是否被占用或已连接。",
               "error")
        return False

    rec = Recognizer(cfg)
    if not rec.init_models():
        cam.release()
        _alert("FaceGuard · 模型加载失败",
               "人脸识别模型加载失败。\n首次运行需联网下载模型，请检查网络后重试。",
               "error")
        return False

    if not name:
        name = _ask_name_dialog()

    log.info("开始为 [%s] 采集人脸", name)

    collected = 0
    target = 8
    last_capture = 0.0
    interval = 0.6
    angles = ["正面", "略左", "略右", "抬头", "低头", "左脸", "右脸", "正面"]
    angle_idx = 0

    fail_count = 0
    while collected < target:
        ok, frame = cam.read()
        if not ok:
            fail_count += 1
            if fail_count > 100:
                _alert("FaceGuard · 摄像头断开", "摄像头读取持续失败，注册已中止。", "error")
                break
            cv2.waitKey(30)  # 保持窗口响应，允许 ESC
            try:
                if cv2.getWindowProperty("FaceGuard Enroll", cv2.WND_PROP_VISIBLE) < 1:
                    break
            except cv2.error:
                pass
            time.sleep(0.05)
            continue
        fail_count = 0
        faces = rec.detect(frame)
        display = frame.copy()
        if faces:
            f = max(faces, key=lambda x: x.area_ratio)
            # 用简洁风格绘制人脸框
            cv2.rectangle(display, (f.x, f.y), (f.x + f.w, f.y + f.h),
                          (255, 140, 0), 1, cv2.LINE_AA)
            # 四角标记
            cl = max(12, min(f.w, f.h) // 6)
            for cx, cy, dx, dy in [(f.x, f.y, cl, 0), (f.x, f.y, 0, cl),
                                    (f.x+f.w, f.y, -cl, 0), (f.x+f.w, f.y, 0, cl),
                                    (f.x, f.y+f.h, cl, 0), (f.x, f.y+f.h, 0, -cl),
                                    (f.x+f.w, f.y+f.h, -cl, 0), (f.x+f.w, f.y+f.h, 0, -cl)]:
                cv2.line(display, (cx, cy), (cx+dx, cy+dy), (255, 140, 0), 2, cv2.LINE_AA)
        # 状态文字
        cv2.putText(display, f"FaceGuard Enroll  {collected}/{target}",
                    (10, 28), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (245, 245, 247), 1, cv2.LINE_AA)
        cv2.putText(display, f"Angle: {angles[min(angle_idx, len(angles)-1)]}",
                    (10, 52), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (142, 142, 147), 1, cv2.LINE_AA)
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
                angle_idx += 1
                last_capture = time.time()
                log.info("已采集 %d/%d", collected, target)

    cam.release()
    cv2.destroyAllWindows()

    if collected >= 3:
        _alert("FaceGuard · 注册成功",
               f"注册完成！共采集 {collected} 张人脸特征。\n"
               f"用户：{name}\n\n现在可以启动 FaceGuard 守护了。",
               "info")
        return True
    _alert("FaceGuard · 注册失败",
           f"采集数量不足（{collected}/8）。\n请确保光线充足、正对摄像头后重试。",
           "warning")
    return False
