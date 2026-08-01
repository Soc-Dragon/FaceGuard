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

# 支持两种入口：
#   1. python -m faceguard         （包模式，相对导入正常）
#   2. python faceguard/__main__.py（脚本模式，需回退到绝对导入）
# PyInstaller 打包用顶层 run.py，走包模式，本回退仅作兜底。
if __package__ in (None, ""):
    # 被当顶层脚本运行，把父目录加入 sys.path 并用绝对导入
    import os
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    from faceguard import __version__
    from faceguard.camera import Camera
    from faceguard.config import LOG_DIR, load_config, save_config
    from faceguard.enroll import enroll_interactive
    from faceguard.guardian import Guardian
    from faceguard.locker import current_executable, is_workstation_locked, lock_workstation, suspend
    from faceguard.notifier import alert_recognition_failed
    from faceguard.overlay import render_overlay
    from faceguard.presence import Presence
    from faceguard.recognizer import Recognizer
    from faceguard.ui import OverlayWindow
else:
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
        try:
            from .locker import set_autostart, is_autostart_set
        except ImportError:
            from faceguard.locker import set_autostart, is_autostart_set
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
    if sys.platform != "win32":
        return
    try:
        import ctypes
        # 唤醒显示器
        ctypes.windll.user32.SendMessageW(0xFFFF, 0x0112, 0xF170, -1)  # WM_SYSCOMMAND, SC_MONITORPOWER on
        # 模拟一次轻量输入唤醒（移动鼠标 0 像素）以触发登录画面人脸检测
        ctypes.windll.user32.mouse_event(0x0001, 0, 0, 0, 0)
        log.info("已发起会话唤醒（keep_unlocked 策略）。")
    except Exception as e:
        log.warning("会话唤醒失败: %s", e)


def _alert_dialog(title: str, message: str, icon: str = "warning") -> None:
    """无控制台模式下弹出对话框（--windowed 打包时唯一可见反馈）。"""
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
    except Exception:
        # tkinter 不可用时写日志（--windowed 下 sys.stdout 为 None，不能用 print）
        log.error("%s: %s", title, message)


def run_guard(cfg: dict, silent: bool = False) -> int:
    """主守护循环。返回退出码：0=正常, 1=摄像头错误, 2=模型错误, 3=未注册。"""
    rcfg = cfg["recognizer"]
    # silent 模式：关闭 overlay、降低日志、不弹对话框
    if silent:
        cfg.setdefault("overlay", {})["enabled"] = False
        log_cfg = cfg.setdefault("log", {})
        if log_cfg.get("level", "INFO").upper() == "INFO":
            log_cfg["level"] = "WARNING"
            logging.getLogger().setLevel(logging.WARNING)

    cam = Camera(rcfg.get("camera_index", 0),
                 rcfg.get("frame_width", 640),
                 rcfg.get("frame_height", 480),
                 rcfg.get("fps", 15))
    if not cam.open():
        log.error("摄像头打开失败，程序退出（退出码 1）")
        if not silent:
            _alert_dialog(
                "FaceGuard · 摄像头错误",
                "无法打开摄像头（序号 %s）。\n\n"
                "请检查：\n"
                "1. 摄像头是否被其他程序占用\n"
                "2. 摄像头是否已连接\n"
                "3. 在「设置」中更换摄像头序号" % rcfg.get("camera_index", 0),
                "error",
            )
        return 1

    rec = Recognizer(cfg)
    if not rec.init_models():
        log.error("模型初始化失败。")
        cam.release()
        if not silent:
            _alert_dialog(
                "FaceGuard · 模型加载失败",
                "人脸识别模型加载失败。\n\n"
                "可能原因：\n"
                "1. 首次运行需联网下载模型\n"
                "2. 模型文件损坏\n\n"
                "请检查网络后重试，或重新安装。",
                "error",
            )
        return 2

    if not rec.has_enrolled():
        log.warning("尚未注册任何人脸！请先运行 --enroll 完成注册。")
        cam.release()
        # 未注册是必须解决的首次设置，即使 silent 也弹窗引导（不能静默退出让用户无感）
        try:
            import tkinter as tk
            from tkinter import messagebox
            root = tk.Tk()
            root.withdraw()
            root.attributes("-topmost", True)
            ans = messagebox.askyesno(
                "FaceGuard · 尚未注册人脸",
                "尚未注册任何人脸，守护无法启动。\n\n"
                "是否立即注册本人人脸？",
                parent=root,
            )
            root.destroy()
            if ans and enroll_interactive(cfg):
                # 注册成功，递归重启守护（这次会跳过未注册分支）
                return run_guard(cfg, silent)
        except Exception as e:
            log.error("无法启动注册引导: %s", e)
        return 3

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
            try:
                ok, frame = cam.read()
                if not ok:
                    time.sleep(0.05)
                    continue

                faces = rec.detect(frame)
                t = time.time()
                owner_name, confidence = (None, 0.0)
                biggest = max(faces, key=lambda x: x.area_ratio) if faces else None

                # 缓存锁屏状态，避免每帧双调用 Win32 API
                locked = is_workstation_locked()

                if biggest and biggest.embedding is not None:
                    name, conf = rec.confirm_owner(biggest.embedding)
                    owner_name, confidence = name, conf
                    if name:
                        # 确认是本人
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

                # overlay 渲染（锁屏且无主人时隐藏，避免 show/hide 竞态闪烁）
                if cfg.get("overlay", {}).get("enabled", True):
                    display = frame.copy()
                    render_overlay(display, faces, owner_name, confidence,
                                   status, cfg, t)
                    overlay.update_frame(display)
                    if locked and not owner_name:
                        overlay.hide()
                    else:
                        overlay.show()
            except Exception:
                log.exception("单帧处理异常，跳过该帧")
                time.sleep(0.05)

    finally:
        overlay.stop()
        cam.release()
        log.info("FaceGuard 守护已停止。")
    return 0


def config_ui(cfg: dict) -> None:
    """液态玻璃风格设置面板（tkinter）。"""
    import tkinter as tk
    from tkinter import messagebox

    # 简洁配色（深色背景 + 激光蓝强调）
    BG_DEEP = "#0A0A0E"          # 深黑背景
    BG_PANEL = "#1C1C1E"         # 面板底
    BG_PANEL_HOVER = "#2C2C2E"
    ACCENT = "#008CFF"           # 激光蓝
    ACCENT_DIM = "#0066CC"
    ACCENT_PURPLE = "#4DA8FF"    # 激光蓝亮
    ACCENT_AMBER = "#FF9500"     # 警告橙
    ACCENT_BLUE = "#008CFF"      # 蓝
    TEXT_PRIMARY = "#F5F5F7"     # Apple 白
    TEXT_SECONDARY = "#8E8E93"   # 副文字
    TEXT_HINT = "#48484A"        # 提示
    BORDER_GLOW = "#2C2C2E"
    DANGER = "#FF3B30"           # 红

    root = tk.Tk()
    root.title("FaceGuard · 设置")
    root.geometry("560x760")
    root.configure(bg=BG_DEEP)

    # 字体：Windows 用 Microsoft YaHei UI（中英文兼优），其他平台回退
    _fn = "Microsoft YaHei UI" if sys.platform == "win32" else "Source Han Sans SC"
    FONT_TITLE = (_fn, 22, "bold")
    FONT_SECTION = (_fn, 13, "bold")
    FONT_LABEL = (_fn, 10)
    FONT_VALUE = (_fn, 10)
    FONT_HINT = (_fn, 9)

    # 顶部标题区
    header = tk.Frame(root, bg=BG_DEEP)
    header.pack(fill="x", padx=24, pady=(20, 4))
    tk.Label(header, text="FaceGuard", font=FONT_TITLE,
             fg=ACCENT, bg=BG_DEEP).pack(anchor="w")
    tk.Label(header, text="液态玻璃 · 人脸解锁守护", font=FONT_HINT,
             fg=TEXT_HINT, bg=BG_DEEP).pack(anchor="w")

    # 内容滚动容器
    canvas = tk.Canvas(root, bg=BG_DEEP, highlightthickness=0, bd=0)
    scroll = tk.Scrollbar(root, orient="vertical", command=canvas.yview,
                          troughcolor=BG_DEEP, bg=BG_PANEL)
    canvas.configure(yscrollcommand=scroll.set)
    scroll.pack(side="right", fill="y")
    canvas.pack(side="left", fill="both", expand=True, padx=(0, 0))
    content = tk.Frame(canvas, bg=BG_DEEP)
    canvas.create_window((0, 0), window=content, anchor="nw", width=540)
    def _resize(e):
        canvas.itemconfig("all", width=e.width)
    canvas.bind("<Configure>", _resize)

    def glass_section(parent, title, subtitle=""):
        """液态玻璃分区：深色圆角面板 + 强调色标题条。"""
        wrap = tk.Frame(parent, bg=BG_DEEP)
        wrap.pack(fill="x", padx=20, pady=6)
        panel = tk.Frame(wrap, bg=BG_PANEL, bd=0, highlightbackground=BORDER_GLOW,
                         highlightthickness=1)
        panel.pack(fill="x")
        # 标题条
        head = tk.Frame(panel, bg=BG_PANEL)
        head.pack(fill="x", padx=16, pady=(10, 0))
        # 强调色小圆点
        dot = tk.Canvas(head, width=8, height=8, bg=BG_PANEL, highlightthickness=0)
        dot.create_oval(0, 0, 8, 8, fill=ACCENT, outline="")
        dot.pack(side="left", padx=(0, 8))
        tk.Label(head, text=title, font=FONT_SECTION,
                 fg=TEXT_PRIMARY, bg=BG_PANEL).pack(side="left")
        if subtitle:
            tk.Label(head, text=subtitle, font=FONT_HINT,
                     fg=TEXT_HINT, bg=BG_PANEL).pack(side="left", padx=8)
        body = tk.Frame(panel, bg=BG_PANEL)
        body.pack(fill="x", padx=16, pady=(8, 14))
        return body

    def glass_entry(parent, label, value, width=18, show=None, hint=""):
        """标签 + 输入框 行。"""
        row = tk.Frame(parent, bg=BG_PANEL)
        row.pack(fill="x", pady=4)
        tk.Label(row, text=label, font=FONT_LABEL, fg=TEXT_SECONDARY,
                 bg=BG_PANEL, width=16, anchor="w").pack(side="left")
        e = tk.Entry(row, font=FONT_VALUE, fg=TEXT_PRIMARY, bg=BG_DEEP,
                     insertbackground=ACCENT, relief="flat", width=width,
                     show=show, bd=0, highlightbackground=BORDER_GLOW,
                     highlightthickness=1, highlightcolor=ACCENT)
        e.insert(0, str(value))
        e.pack(side="left", ipady=5, padx=4)
        e.config(justify="left")
        if hint:
            tk.Label(row, text=hint, font=FONT_HINT, fg=TEXT_HINT,
                     bg=BG_PANEL).pack(side="left", padx=4)
        return e

    def glass_toggle(parent, label, var):
        """液态开关（Checkbutton 美化）。"""
        row = tk.Frame(parent, bg=BG_PANEL)
        row.pack(fill="x", pady=3)
        cb = tk.Checkbutton(row, text=label, font=FONT_LABEL, fg=TEXT_PRIMARY,
                            bg=BG_PANEL, selectcolor=BG_DEEP, activebackground=BG_PANEL,
                            activeforeground=ACCENT, variable=var, anchor="w",
                            relief="flat", highlightthickness=0)
        cb.pack(anchor="w")

    # === 识别引擎 ===
    rb = glass_section(content, "识别引擎", "Recognition")
    e_thr = glass_entry(rb, "置信度阈值", cfg["recognizer"]["confidence_threshold"],
                        width=10, hint="0.3-0.8")
    e_cf = glass_entry(rb, "确认帧数", cfg["recognizer"]["confirm_frames"], width=10)
    e_cam = glass_entry(rb, "摄像头序号", cfg["recognizer"]["camera_index"], width=10)
    e_fps = glass_entry(rb, "识别帧率", cfg["recognizer"].get("fps", 15), width=10, hint="fps")

    # === 识别模型选择 ===
    mb = glass_section(content, "识别模型", "Model · 三选一")
    model_var = tk.StringVar(value=cfg["recognizer"].get("recognizer_type", "sface"))
    for mt, ml, md in [("sface", "YuNet + SFace", "默认 · 99.5% · 38MB"),
                       ("mobilefacenet", "MobileFaceNet", "轻量 · 快 · 5MB"),
                       ("arcface", "ArcFace ResNet50", "高精度 · 99.8% · 170MB")]:
        tk.Radiobutton(mb, text=f"{ml}  ({md})", font=FONT_LABEL, fg=TEXT_PRIMARY,
                       bg=BG_PANEL, selectcolor=BG_DEEP, activebackground=BG_PANEL,
                       activeforeground=ACCENT, variable=model_var, value=mt,
                       anchor="w", relief="flat", highlightthickness=0).pack(anchor="w", pady=2)

    # === 自适应学习 ===
    ab = glass_section(content, "自适应学习", "Adaptive · 记忆脸部变化")
    var_adaptive = tk.BooleanVar(value=cfg.get("adaptive", {}).get("enabled", True))
    glass_toggle(ab, "成功解锁后增量学习", var_adaptive)
    e_max = glass_entry(ab, "每用户最多", cfg.get("adaptive", {}).get("max_samples_per_user", 30), width=10, hint="样本")
    e_cool = glass_entry(ab, "冷却秒数", cfg.get("adaptive", {}).get("cooldown_seconds", 300), width=10)

    # === 邮件告警 ===
    nb = glass_section(content, "邮件告警", "失败抓拍 / 入侵提醒")
    e_host = glass_entry(nb, "SMTP 服务器", cfg["notify"]["smtp_host"], width=22)
    e_sender = glass_entry(nb, "发件邮箱", cfg["notify"]["sender"], width=22)
    e_pwd = glass_entry(nb, "授权码", cfg["notify"]["password"], width=22, show="●", hint="非登录密码")
    e_to = glass_entry(nb, "收件邮箱", cfg["notify"]["to"], width=22)
    e_cd = glass_entry(nb, "冷却秒数", cfg["notify"]["cooldown_seconds"], width=10)

    # === 离开锁屏休眠 ===
    pb = glass_section(content, "离开锁屏休眠", "Presence")
    e_lock = glass_entry(pb, "离开锁屏(秒)", cfg["presence"]["absence_lock_seconds"], width=10)
    e_sleep = glass_entry(pb, "锁屏休眠(秒)", cfg["presence"]["sleep_after_seconds"], width=10)
    e_nf = glass_entry(pb, "无脸判定(秒)", cfg["presence"]["no_face_threshold_seconds"], width=10)

    # === 开关 ===
    gb = glass_section(content, "功能开关", "Toggles")
    var_guard = tk.BooleanVar(value=cfg["guardian"]["enabled"])
    glass_toggle(gb, "身后入侵守护", var_guard)
    var_auto = tk.BooleanVar(value=cfg["autostart"]["enabled"])
    glass_toggle(gb, "注册表开机自启", var_auto)
    var_overlay = tk.BooleanVar(value=cfg["overlay"]["enabled"])
    glass_toggle(gb, "识别画面液态玻璃叠加", var_overlay)

    # === 保存按钮（液态强调）===
    def save():
        try:
            cfg["recognizer"]["confidence_threshold"] = float(e_thr.get())
            cfg["recognizer"]["confirm_frames"] = int(e_cf.get())
            cfg["recognizer"]["camera_index"] = int(e_cam.get())
            cfg["recognizer"]["fps"] = int(e_fps.get())
            cfg["recognizer"]["recognizer_type"] = model_var.get()
            cfg.setdefault("adaptive", {})
            cfg["adaptive"]["enabled"] = var_adaptive.get()
            cfg["adaptive"]["max_samples_per_user"] = int(e_max.get())
            cfg["adaptive"]["cooldown_seconds"] = int(e_cool.get())
            cfg["notify"]["smtp_host"] = e_host.get().strip()
            cfg["notify"]["sender"] = e_sender.get().strip()
            cfg["notify"]["password"] = e_pwd.get().strip()
            cfg["notify"]["to"] = e_to.get().strip()
            cfg["notify"]["cooldown_seconds"] = int(e_cd.get())
            cfg["presence"]["absence_lock_seconds"] = int(e_lock.get())
            cfg["presence"]["sleep_after_seconds"] = int(e_sleep.get())
            cfg["presence"]["no_face_threshold_seconds"] = int(e_nf.get())
            cfg["guardian"]["enabled"] = var_guard.get()
            cfg["autostart"]["enabled"] = var_auto.get()
            cfg["overlay"]["enabled"] = var_overlay.get()
            save_config(cfg)
            messagebox.showinfo("成功", "设置已保存。")
        except Exception as ex:
            messagebox.showerror("错误", str(ex))

    btn_frame = tk.Frame(root, bg=BG_DEEP)
    btn_frame.pack(fill="x", padx=20, pady=14)
    save_btn = tk.Button(btn_frame, text="  保存设置  ", command=save,
                         font=(_fn, 12, "bold"), fg="#0A1A12",
                         bg=ACCENT, activebackground=ACCENT_DIM,
                         activeforeground="#0A1A12", relief="flat", bd=0,
                         cursor="hand2", padx=30, pady=10)
    save_btn.pack()

    # 更新滚动区域
    content.update_idletasks()
    canvas.configure(scrollregion=canvas.bbox("all"))
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
        # --windowed 下 sys.stdout 可能为 None，用 _alert_dialog 替代 print
        _alert_dialog("FaceGuard", f"FaceGuard v{__version__}", "info")
        return 0

    cfg = load_config()
    setup_logging(cfg)

    if args.config:
        try:
            config_ui(cfg)
        except Exception as e:
            log.exception("设置面板异常")
            _alert_dialog("FaceGuard · 设置面板错误", f"无法打开设置面板：\n{e}", "error")
            return 1
        return 0

    if args.enroll:
        try:
            ok = enroll_interactive(cfg)
            return 0 if ok else 1
        except Exception as e:
            log.exception("注册异常")
            _alert_dialog("FaceGuard · 注册错误", f"注册过程出错：\n{e}", "error")
            return 1

    # 默认：启动守护
    try:
        return run_guard(cfg, silent=args.silent)
    except Exception as e:
        log.exception("守护异常退出")
        if not args.silent:
            _alert_dialog(
                "FaceGuard · 异常退出",
                f"程序遇到错误：\n{e}\n\n请截图此错误并反馈。",
                "error",
            )
        return 1


if __name__ == "__main__":
    sys.exit(main())
