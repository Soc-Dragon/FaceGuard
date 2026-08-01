"""配置管理：加载 / 保存 / 默认值。

所有可调参数集中在这里，用户可通过编辑 config.json 或运行
``python -m faceguard --config`` 调出设置面板修改。
"""

from __future__ import annotations

import json
import os
from copy import deepcopy
from pathlib import Path

# 运行期数据目录：C:\\Users\\<u>\\AppData\\Roaming\\FaceGuard
# 防御: APPDATA 异常时兜底到用户主目录
def _resolve_app_dir() -> Path:
    candidates = []
    appdata = os.environ.get("APPDATA", "").strip()
    if appdata:
        candidates.append(Path(appdata))
    # Windows 备用: LOCALAPPDATA
    localappdata = os.environ.get("LOCALAPPDATA", "").strip()
    if localappdata:
        candidates.append(Path(localappdata))
    # 兜底: 用户主目录
    candidates.append(Path.home() / ".faceguard")

    for base in candidates:
        try:
            if not base or str(base) in ("", "."):
                continue
            d = base / "FaceGuard"
            d.mkdir(parents=True, exist_ok=True)
            if d.exists():
                return d
        except (OSError, PermissionError, ValueError):
            continue
    # 最后兜底: 当前工作目录
    return Path.cwd() / "FaceGuard"


APP_DIR = _resolve_app_dir()

CONFIG_PATH = APP_DIR / "config.json"
DATA_DIR = APP_DIR / "data"
MODELS_DIR = APP_DIR / "models"
LOG_DIR = APP_DIR / "logs"
CAPTURE_DIR = APP_DIR / "captures"

for _d in (DATA_DIR, MODELS_DIR, LOG_DIR, CAPTURE_DIR):
    try:
        _d.mkdir(parents=True, exist_ok=True)
    except (OSError, PermissionError):
        pass

# 默认配置 —— 所有数字均可在设置中由用户自行调整
DEFAULTS = {
    "version": "2.1.0",
    # 识别引擎
    "recognizer": {
        "confidence_threshold": 0.55,   # SFace 余弦相似度阈值，>=0.5 即认定为本人
        "confirm_frames": 3,            # 连续命中 N 帧才判定解锁，提升稳定性
        "match_window": 5,              # 滑动窗口帧数
        "camera_index": 0,             # 摄像头序号
        "frame_width": 640,
        "frame_height": 480,
        "fps": 15,                      # 识别帧率，降低 CPU 占用
        "recognizer_type": "sface",     # 识别模型: sface/mobilefacenet/arcface
    },
    # 自适应学习（每次成功解锁后增量更新特征库）
    "adaptive": {
        "enabled": True,                # 总开关
        "max_samples_per_user": 30,     # 每个用户最多保留学习样本数
        "learn_threshold": 0.7,         # 仅在相似度 >= 该值时学习（避免学到错误特征）
        "cooldown_seconds": 300,        # 学习冷却（同一用户 5 分钟内不重复学习）
    },
    # 邮件告警（识别失败时抓拍并寄出）
    "notify": {
        "enabled": True,
        "smtp_host": "smtp.qq.com",
        "smtp_port": 465,
        "smtp_ssl": True,
        "sender": "",
        "password": "",                # QQ 邮箱授权码，非登录密码
        "to": "",
        "cooldown_seconds": 60,        # 同一告警冷却，避免刷屏
    },
    # 身后入侵守护
    "guardian": {
        "enabled": True,
        "multi_face_notify": True,     # 画面中出现 >1 张人脸即告警
        "min_face_area_ratio": 0.015,  # 过滤太小的远处人脸噪点
        "notify_sound": True,
    },
    # 离开锁屏休眠
    "presence": {
        "enabled": True,
        "absence_lock_seconds": 300,   # 离开 5 分钟后锁屏
        "sleep_after_seconds": 300,    # 锁屏后再 5 分钟未解锁则休眠
        "no_face_threshold_seconds": 10, # 连续无脸 N 秒判定为离开
    },
    # 注册表常驻
    "autostart": {
        "enabled": True,
        "registry_key": "FaceGuard",
    },
    # 识别画面 overlay
    "overlay": {
        "enabled": True,
        "opacity": 0.9,
        "show_landmarks": True,
        "show_scanline": True,
        "show_confidence": True,
    },
    # 安全解锁注入
    "unlock": {
        "method": "session_unlock",   # session_unlock | keep_unlocked
    },
    # 日志
    "log": {
        "level": "INFO",
        "max_bytes": 1048576,
        "backup_count": 7,
    },
}


def _deep_merge(base: dict, override: dict) -> dict:
    """递归合并：override 覆盖 base，数值做类型校验。"""
    out = deepcopy(base)
    for k, v in (override or {}).items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = _deep_merge(out[k], v)
        else:
            default_val = out.get(k)
            if isinstance(default_val, bool):
                # bool 字段只接受 bool
                out[k] = v if isinstance(v, bool) else default_val
            elif isinstance(default_val, (int, float)):
                # 数值字段做类型转换
                if isinstance(v, bool):
                    out[k] = default_val
                elif isinstance(v, (int, float)):
                    out[k] = v
                else:
                    try:
                        out[k] = type(default_val)(v)
                    except (TypeError, ValueError):
                        out[k] = default_val
            elif isinstance(default_val, str):
                # 字符串字段只接受 str
                out[k] = v if isinstance(v, str) else default_val
            else:
                out[k] = v
    return out


def load_config() -> dict:
    """加载配置，缺失项用默认值补全。"""
    cfg = deepcopy(DEFAULTS)
    if CONFIG_PATH.exists():
        try:
            raw = CONFIG_PATH.read_text(encoding="utf-8")
            cfg = _deep_merge(cfg, json.loads(raw))
        except (json.JSONDecodeError, OSError) as e:
            # 备份损坏的配置
            try:
                import shutil
                import time
                bak = CONFIG_PATH.with_suffix(f".json.bak.corrupt.{int(time.time())}")
                shutil.copy2(CONFIG_PATH, bak)
            except OSError:
                pass
            # 用 print 而非 log（logging 可能未初始化）
            print(f"[FaceGuard] 配置文件损坏，使用默认值: {e}", flush=True)
    cfg.setdefault("version", DEFAULTS["version"])
    return cfg


def save_config(cfg: dict) -> bool:
    import os
    try:
        tmp = CONFIG_PATH.with_suffix(".json.tmp")
        tmp.write_text(
            json.dumps(cfg, indent=2, ensure_ascii=False), encoding="utf-8"
        )
        os.replace(tmp, CONFIG_PATH)
        return True
    except (OSError, PermissionError, TypeError, ValueError) as e:
        print(f"[FaceGuard] 配置保存失败: {e}", flush=True)
        return False


def ensure_example_config(path: Path) -> None:
    """把默认配置写成 config.example.json 供用户参考。"""
    path.write_text(
        json.dumps(DEFAULTS, indent=2, ensure_ascii=False), encoding="utf-8"
    )
