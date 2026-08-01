@echo off
chcp 65001 >nul
REM FaceGuard 卸载清理：移除注册表自启项 + 运行时数据

REM 移除启动项
reg delete "HKCU\Software\Microsoft\Windows\CurrentVersion\Run" /v FaceGuard /f >nul 2>&1
echo [FaceGuard] 已移除开机自启注册表项。

REM 终止运行中的进程
taskkill /F /IM FaceGuard.exe >nul 2>&1

echo [FaceGuard] 用户数据已保留于 %APPDATA%\FaceGuard

echo.
echo [FaceGuard] 卸载完成。
