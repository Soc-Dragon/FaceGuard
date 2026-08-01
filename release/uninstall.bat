@echo off
chcp 65001 >nul
REM FaceGuard 卸载清理：移除注册表自启项 + 运行时数据

REM 移除启动项
reg delete "HKCU\Software\Microsoft\Windows\CurrentVersion\Run" /v FaceGuard /f >nul 2>&1
echo [FaceGuard] 已移除开机自启注册表项。

REM 终止运行中的进程
taskkill /F /IM FaceGuard.exe >nul 2>&1

REM 询问是否删除用户数据（人脸库 / 配置 / 抓拍）
set /p CONFIRM=是否同时删除用户数据（人脸库、配置、抓拍照片）？[y/N]:
if /i "%CONFIRM%"=="y" (
    rmdir /S /Q "%APPDATA%\FaceGuard" 2>nul
    echo [FaceGuard] 用户数据已删除。
) else (
    echo [FaceGuard] 用户数据已保留于 %%APPDATA%%\FaceGuard
)

echo.
echo [FaceGuard] 卸载完成。
pause
