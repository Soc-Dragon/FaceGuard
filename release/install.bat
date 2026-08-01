@echo off
chcp 65001 >nul
REM FaceGuard 安装后处理：写入注册表自启项
REM （Inno Setup 已完成文件复制，这里补充运行时配置）

set "EXE=%~dp0FaceGuard.exe"
if not exist "%EXE%" (
    echo [FaceGuard] 未找到 FaceGuard.exe，请重新安装。
    exit /b 1
)

REM 写入 HKCU 启动项
reg add "HKCU\Software\Microsoft\Windows\CurrentVersion\Run" /v FaceGuard /t REG_SZ /d "\"%EXE%\" --silent" /f >nul
if %errorlevel%==0 (
    echo [FaceGuard] 已写入开机自启注册表项。
) else (
    echo [FaceGuard] 警告：注册表写入失败，请以管理员身份重试。
)

echo.
echo [FaceGuard] 安装完成！
echo    下一步：从开始菜单运行 "FaceGuard 注册人脸" 完成首次采集。
echo.
