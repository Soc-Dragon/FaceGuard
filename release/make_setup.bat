@echo off
chcp 65001 >nul
REM FaceGuard 一键打包脚本：PyInstaller 生成 exe + Inno Setup 生成 Setup.exe

setlocal
cd /d "%~dp0\.."

echo ===== [1/2] PyInstaller 打包 FaceGuard.exe =====
python build.py
if errorlevel 1 (
    echo [错误] PyInstaller 打包失败。
    pause
    exit /b 1
)

echo.
echo ===== [2/2] Inno Setup 编译 FaceGuard-Setup.exe =====
where iscc >nul 2>nul
if errorlevel 1 (
    if exist "C:\Program Files (x86)\Inno Setup 6\ISCC.exe" (
        set "ISCC=C:\Program Files (x86)\Inno Setup 6\ISCC.exe"
    ) else (
        echo [错误] 未找到 Inno Setup (ISCC.exe)，请安装 Inno Setup 6。
        pause
        exit /b 1
    )
) else (
    set "ISCC=iscc"
)

"%ISCC%" release\FaceGuard.iss
if errorlevel 1 (
    echo [错误] Inno Setup 编译失败。
    pause
    exit /b 1
)

echo.
echo ===== 完成！=====
echo 安装包位于：dist_setup\FaceGuard-Setup.exe
pause
