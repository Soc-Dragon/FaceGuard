"""Windows 系统操作：锁屏、休眠、注册表常驻、会话状态。

仅依赖 ctypes + winreg（均内置），无需 pywin32，打包更轻。
"""

from __future__ import annotations

import ctypes
import sys
from pathlib import Path

try:
    import winreg  # Windows only
except ImportError:  # 非 Windows（沙盒验证用）
    winreg = None

from .config import APP_DIR


# ---------- 锁屏 / 休眠 ----------

def lock_workstation() -> bool:
    """立即锁定工作站。"""
    if sys.platform != "win32":
        return False
    try:
        return bool(ctypes.windll.user32.LockWorkStation())
    except Exception:
        return False


def suspend(sleep: bool = True) -> bool:
    """进入睡眠(sleep=True)或休眠(sleep=False)。

    SetSuspendState(Hibernate, ForceCritical, DisableWakeEvent)
    """
    if sys.platform != "win32":
        return False
    try:
        hibernate = 0 if sleep else 1
        return bool(ctypes.windll.powrprof.SetSuspendState(hibernate, 0, 0))  # ForceCritical=0
    except Exception:
        return False


def is_workstation_locked() -> bool:
    """粗略判断当前是否处于锁屏状态。"""
    if sys.platform != "win32":
        return False
    try:
        import ctypes.wintypes
        user32 = ctypes.windll.user32
        DESKTOP_READOBJECTS = 0x0001
        DESKTOP_READCONTROL = 0x0002
        # 设置函数签名（64位句柄正确处理）
        user32.OpenInputDesktop.restype = ctypes.wintypes.HDESK
        user32.OpenInputDesktop.argtypes = [ctypes.wintypes.BOOL, ctypes.wintypes.BOOL, ctypes.wintypes.DWORD]
        user32.GetUserObjectInformationW.restype = ctypes.wintypes.BOOL
        user32.GetUserObjectInformationW.argtypes = [ctypes.wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p, ctypes.wintypes.DWORD, ctypes.POINTER(ctypes.wintypes.DWORD)]
        user32.CloseDesktop.restype = ctypes.wintypes.BOOL
        user32.CloseDesktop.argtypes = [ctypes.wintypes.HDESK]

        hdesk = user32.OpenInputDesktop(False, False, DESKTOP_READOBJECTS | DESKTOP_READCONTROL)
        if not hdesk:
            return True
        buf = ctypes.create_unicode_buffer(256)
        ok = user32.GetUserObjectInformationW(hdesk, 2, buf, 512, None)
        user32.CloseDesktop(hdesk)
        if not ok:
            return False  # 无法判定，按未锁处理
        name = buf.value
        return name.lower() != "default"
    except Exception:
        return False


# ---------- 注册表常驻 ----------

RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"


def set_autostart(exe_path: Path | str, key_name: str = "FaceGuard") -> bool:
    """写入 HKCU 启动项，开机 / 登录后自动运行。"""
    if winreg is None:
        return False
    try:
        val = f'"{Path(exe_path)}" --silent'
        with winreg.CreateKey(winreg.HKEY_CURRENT_USER, RUN_KEY) as k:
            winreg.SetValueEx(k, key_name, 0, winreg.REG_SZ, val)
        return True
    except OSError as e:
        print(f"[FaceGuard] 写入注册表失败: {e}", file=sys.stderr)
        return False


def clear_autostart(key_name: str = "FaceGuard") -> bool:
    """移除启动项。"""
    if winreg is None:
        return False
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_SET_VALUE) as k:
            winreg.DeleteValue(k, key_name)
        return True
    except FileNotFoundError:
        return True
    except OSError as e:
        print(f"[FaceGuard] 清除注册表失败: {e}", file=sys.stderr)
        return False


def is_autostart_set(key_name: str = "FaceGuard") -> bool:
    if winreg is None:
        return False
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_READ) as k:
            winreg.QueryValueEx(k, key_name)
        return True
    except FileNotFoundError:
        return False
    except OSError:
        return False


# ---------- 可执行路径辅助 ----------

def current_executable() -> Path:
    """返回打包后 / 开发环境下的可执行路径。"""
    if getattr(sys, "frozen", False):
        return Path(sys.executable)
    argv0 = sys.argv[0] if sys.argv else ""
    if not argv0:
        return Path(sys.executable).resolve()
    return Path(argv0).resolve()
