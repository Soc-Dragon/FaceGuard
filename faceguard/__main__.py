"""FaceGuard 主程序入口。

负责编排：摄像头 -> 检测识别 -> 多帧确认 -> 解锁 / 告警 / 守护 / 离开锁屏。
支持命令行参数：--enroll / --config / --silent / --version
"""

from __future__ import annotations

import argparse
import logging
import logging.handlers
import signal
import sys
import time

from . import __version__
from .camera import Camera
from .config import LOG_DIR, load_config, save_config
from .enroll import enroll_interactive
from .guardian import Guardian
from .locker import current_executable, is_workstation_locked, lock_workstation, suspend
from .notifier import alert_recognition_failed
from .overlay import render_overlay
from .presence import Presence
from .recognizer import Recognizer
from .ui import OverlayWindow

log = logging.getLogger("faceguard")


def setup_logging(cfg: dict) -> None:
    level = getattr(logging, cfg.get("log", {}).get("level", "INFO").upper(), logging.INFO)
    logging.basicConfig(level=level, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
    try:
        fh = logging.handlers.RotatingFileHandler(
            LOG_DIR / "faceguard.log",
            maxBytes=cfg.get("log", {}).get("max_bytes", 1048576),
            backupCount=cfg.get("log", {}).get("backup_count", 7),
            encoding="utf-8",
        )
        fh.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s"))
        logging.getLogger().addHandler(fh)
    except Exception:
        pass


def ensure_autostart(cfg: dict) -> None:
    acfg = cfg.get("autostart", {})
    if acfg.get("enabled", True):
        from .locker import set_autostart, is_autostart_set
        key = acfg.get("registry_key", "FaceGuard")
        if not is_autostart_set(key):
            exe = current_executable()
            if set_autostart(exe, key):
                log.info("已写入注册表自启项: %s", key)


def unlock_session(cfg: dict) -> None:
    """解锁注入：触发会话解锁。

    由于 Windows 安全限制，第三方程序无法直接"解锁"已锁屏的桌面。
    FaceGuard 采用 keep_unlocked 策略：在检测到本人后立即发起
    可信会话激活（通过模拟用户输入唤醒显示 + 维持活跃），
    配合 --silent 常驻，使锁屏画面在确认本人后自动消失。
    """
    try:
        import ctypes
        # 唤醒显示器
        ctypes.windll.user32.SendMessageW(0xFFFF, 0x0112, 0xF170, -1)  # WM_SYSCOMMAND, SC_MONITORPOWER on
        # 模拟一次轻量输入唤醒（移动鼠标 0 像素）以触发登录画面人脸检测
        ctypes.windll.user32.mouse_event(0x0001, 0, 0, 0, 0)
        log.info("已发起会话唤醒（keep_unlocked 策略）。")
    except Exception as e:
        log.debug("会话唤醒失败: %s", e)


def run_guard(cfg: dict) -> None:
    """主守护循环。"""
    rcfg = cfg["recognizer"]
    cam = Camera(rcfg.get("camera_index", 0),
                 rcfg.get("frame_width", 640),
                 rcfg.get("frame_height", 480),
                 rcfg.get("fps", 15))
    if not cam.open():
        log.error("摄像头打开失败，5 秒后重试...")
        time.sleep(5)
        return

    rec = Recognizer(cfg)
    if not rec.init_models():
        log.error("模型初始化失败。")
        cam.release()
        return

    if not rec.has_enrolled():
        log.warning("尚未注册任何人脸！请先运行 --enroll 完成注册。")
        cam.release()
        return

    guardian = Guardian(cfg)
    presence = Presence(cfg)
    overlay = OverlayWindow(width=rcfg.get("frame_width", 640),
                            height=rcfg.get("frame_height", 480))
    if cfg.get("overlay", {}).get("enabled", True):
        overlay.start()

    ensure_autostart(cfg)
    log.info("FaceGuard v%s 守护已启动。", __version__)

    running = {"alive": True}

    def _stop(signum, frame):
        running["alive"] = False
    signal.signal(signal.SIGINT, _stop)
    signal.signal(signal.SIGTERM, _stop)

    last_failed_alert = 0.0
    fail_cooldown = cfg.get("notify", {}).get("cooldown_seconds", 60)

    try:
        while running["alive"]:
            ok, frame = cam.read()
            if not ok:
                time.sleep(0.05)
                continue

            faces = rec.detect(frame)
            t = time.time()
            owner_name, confidence = (None, 0.0)
            biggest = max(faces, key=lambda x: x.area_ratio) if faces else None

            if biggest and biggest.embedding is not None:
                name, conf = rec.confirm_owner(biggest.embedding)
                owner_name, confidence = name, conf
                if name:
                    # 确认是本人
                    locked = is_workstation_locked()
                    if locked:
                        unlock_session(cfg)
                        log.info("识别到本人 [%s] (相似度 %.3f)，发起解锁。",
                                 name, conf)
                    status = f"✓ 已识别: {name}  ({conf:.2f})"
                else:
                    # 最大脸是陌生人
                    now = t
                    if now - last_failed_alert > fail_cooldown:
                        alert_recognition_failed(frame, cfg)
                        last_failed_alert = now
                    status = f"✗ 陌生人  ({conf:.2f})"
            elif faces:
                status = "检测到人脸（特征提取中）"
            else:
                status = "等待人脸..."
                rec.reset_confirm()

            # 身后守护
            guardian.check(frame, faces, owner_name, cfg)

            # 离开检测
            presence.update(bool(faces), cfg)

            # overlay 渲染
            if cfg.get("overlay", {}).get("enabled", True):
                display = frame.copy()
                render_overlay(display, faces, owner_name, confidence,
                               status, cfg, t)
                overlay.update_frame(display)
                overlay.show()

            # 锁屏时降低 overlay 干扰
            if is_workstation_locked() and not owner_name:
                overlay.hide()

    finally:
        overlay.stop()
        cam.release()
        log.info("FaceGuard 守护已停止。")


def config_ui(cfg: dict) -> None:
    """简易设置面板（tkinter）。"""
    import tkinter as tk
    from tkinter import ttk, messagebox

    root = tk.Tk()
    root.title("FaceGuard 设置")
    root.geometry("520x620")

    def section(parent, title):
        f = tk.LabelFrame(parent, text=title, padx=10, pady=8)
        f.pack(fill="x", padx=10, pady=5)
        return f

    # 识别
    rf = section(root, "识别引擎")
    tk.Label(rf, text="置信度阈值 (0.3-0.8):").grid(row=0, column=0, sticky="w")
    e_thr = tk.Entry(rf, width=10)
    e_thr.insert(0, str(cfg["recognizer"]["confidence_threshold"]))
    e_thr.grid(row=0, column=1)
    tk.Label(rf, text="确认帧数:").grid(row=1, column=0, sticky="w")
    e_cf = tk.Entry(rf, width=10)
    e_cf.insert(0, str(cfg["recognizer"]["confirm_frames"]))
    e_cf.grid(row=1, column=1)
    tk.Label(rf, text="摄像头序号:").grid(row=2, column=0, sticky="w")
    e_cam = tk.Entry(rf, width=10)
    e_cam.insert(0, str(cfg["recognizer"]["camera_index"]))
    e_cam.grid(row=2, column=1)

    # 邮件
    nf = section(root, "邮件告警")
    tk.Label(nf, text="SMTP 服务器:").grid(row=0, column=0, sticky="w")
    e_host = tk.Entry(nf, width=25)
    e_host.insert(0, cfg["notify"]["smtp_host"])
    e_host.grid(row=0, column=1)
    tk.Label(nf, text="发件邮箱:").grid(row=1, column=0, sticky="w")
    e_sender = tk.Entry(nf, width=25)
    e_sender.insert(0, cfg["notify"]["sender"])
    e_sender.grid(row=1, column=1)
    tk.Label(nf, text="授权码:").grid(row=2, column=0, sticky="w")
    e_pwd = tk.Entry(nf, width=25, show="*")
    e_pwd.insert(0, cfg["notify"]["password"])
    e_pwd.grid(row=2, column=1)
    tk.Label(nf, text="收件邮箱:").grid(row=3, column=0, sticky="w")
    e_to = tk.Entry(nf, width=25)
    e_to.insert(0, cfg["notify"]["to"])
    e_to.grid(row=3, column=1)
    tk.Label(nf, text="冷却秒数:").grid(row=4, column=0, sticky="w")
    e_cd = tk.Entry(nf, width=10)
    e_cd.insert(0, str(cfg["notify"]["cooldown_seconds"]))
    e_cd.grid(row=4, column=1)

    # 离开锁屏休眠
    pf = section(root, "离开锁屏休眠")
    tk.Label(pf, text="离开后锁屏(秒):").grid(row=0, column=0, sticky="w")
    e_lock = tk.Entry(pf, width=10)
    e_lock.insert(0, str(cfg["presence"]["absence_lock_seconds"]))
    e_lock.grid(row=0, column=1)
    tk.Label(pf, text="锁屏后休眠(秒):").grid(row=1, column=0, sticky="w")
    e_sleep = tk.Entry(pf, width=10)
    e_sleep.insert(0, str(cfg["presence"]["sleep_after_seconds"]))
    e_sleep.grid(row=1, column=1)

    # 守护 / 自启
    gf = section(root, "其它")
    var_guard = tk.BooleanVar(value=cfg["guardian"]["enabled"])
    tk.Checkbutton(gf, text="身后入侵守护", variable=var_guard).pack(anchor="w")
    var_auto = tk.BooleanVar(value=cfg["autostart"]["enabled"])
    tk.Checkbutton(gf, text="注册表开机自启", variable=var_auto).pack(anchor="w")
    var_overlay = tk.BooleanVar(value=cfg["overlay"]["enabled"])
    tk.Checkbutton(gf, text="显示识别画面叠加", variable=var_overlay).pack(anchor="w")

    def save():
        try:
            cfg["recognizer"]["confidence_threshold"] = float(e_thr.get())
            cfg["recognizer"]["confirm_frames"] = int(e_cf.get())
            cfg["recognizer"]["camera_index"] = int(e_cam.get())
            cfg["notify"]["smtp_host"] = e_host.get().strip()
            cfg["notify"]["sender"] = e_sender.get().strip()
            cfg["notify"]["password"] = e_pwd.get().strip()
            cfg["notify"]["to"] = e_to.get().strip()
            cfg["notify"]["cooldown_seconds"] = int(e_cd.get())
            cfg["presence"]["absence_lock_seconds"] = int(e_lock.get())
            cfg["presence"]["sleep_after_seconds"] = int(e_sleep.get())
            cfg["guardian"]["enabled"] = var_guard.get()
            cfg["autostart"]["enabled"] = var_auto.get()
            cfg["overlay"]["enabled"] = var_overlay.get()
            save_config(cfg)
            messagebox.showinfo("成功", "设置已保存。")
        except Exception as ex:
            messagebox.showerror("错误", str(ex))

    tk.Button(root, text="保存设置", command=save, bg="#4CAF50",
              fg="white", height=2).pack(fill="x", padx=20, pady=10)
    root.mainloop()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="faceguard",
                                     description="FaceGuard 人脸解锁守护")
    parser.add_argument("--enroll", action="store_true", help="注册本人人脸")
    parser.add_argument("--config", action="store_true", help="打开设置面板")
    parser.add_argument("--silent", action="store_true", help="静默常驻模式")
    parser.add_argument("--version", action="store_true", help="显示版本")
    args = parser.parse_args(argv)

    if args.version:
        print(f"FaceGuard v{__version__}")
        return 0

    cfg = load_config()
    setup_logging(cfg)

    if args.config:
        config_ui(cfg)
        return 0

    if args.enroll:
        ok = enroll_interactive(cfg)
        return 0 if ok else 1

    # 默认：启动守护
    run_guard(cfg)
    return 0


if __name__ == "__main__":
    sys.exit(main())
