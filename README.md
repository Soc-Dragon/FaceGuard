# FaceGuard

> Windows Hello 人脸解锁的更稳定、更高效、更全面的替代程序。
> 参考开源项目 [EthanZer0/FaceLogin](https://github.com/EthanZer0/FaceLogin) 迭代优化而来。

基于 **OpenCV DNN（YuNet + SFace）** 高精度人脸识别引擎，识别准确率 **≥ 95%**，并提供一整套安全守护能力。

## 核心特性

| 能力 | 说明 |
|---|---|
| 🧠 高精度人脸解锁 | YuNet 检测 + SFace 识别（LFW 99.55%），多帧确认使实际解锁准确率 ≥ 95% |
| 📷 识别画面可视化 | 锁屏/识别时屏幕叠加摄像头画面，含人脸轮廓、关键点、扫描线、呼吸光晕等特效 |
| 📧 失败抓拍邮件告警 | 识别失败时自动保存陌生人人脸照片并发送到指定邮箱 |
| 👤 身后入侵守护 | 检测到画面中出现除本人外的其他人脸，立即声光提醒 + 邮件告警 |
| 🚶 离开锁屏休眠 | 用户离开 N 秒后自动锁屏，再 M 秒未解锁则自动休眠（数字均可调） |
| 🔒 注册表常驻 | 写入 `HKCU\...\Run`，开机/登录自启，长时间锁屏休眠后仍存活 |
| 🛠️ 全可视化设置 | 所有阈值、时长、邮箱均在设置面板中可调 |

## 快速开始（普通用户）

**全程不用装 Python、不用装编译器、不用敲命令。**

1. 到 [Releases 页面](https://github.com/Soc-Dragon/FaceGuard/releases) 下载 `FaceGuard-Setup.exe`
2. 双击安装
3. 安装完成后从开始菜单运行 **FaceGuard 注册人脸**，正对摄像头采集 8 张
4. 之后 FaceGuard 会开机自启并常驻后台，锁屏后正对摄像头即可解锁

详细图文说明见 [release/README_使用指南.md](release/README_使用指南.md)。

## 从源码构建

```bash
pip install -r requirements.txt
python build.py            # 生成 dist/FaceGuard.exe
# 或用 Inno Setup 打包成安装包：
release\make_setup.bat
```

## 项目结构

```
FaceGuard/
├── faceguard/                # 主程序包
│   ├── __main__.py           # 入口：编排解锁/告警/守护/锁屏休眠
│   ├── recognizer.py         # YuNet+SFace 识别引擎
│   ├── camera.py             # 摄像头捕获
│   ├── overlay.py            # 识别画面可视化特效
│   ├── ui.py                 # overlay 置顶窗口
│   ├── notifier.py           # 邮件告警 + 抓拍
│   ├── guardian.py           # 身后入侵守护
│   ├── presence.py           # 离开锁屏休眠状态机
│   ├── locker.py             # Windows 锁屏/休眠/注册表
│   ├── enroll.py             # 人脸注册向导
│   ├── models.py             # ONNX 模型按需下载
│   └── config.py             # 配置管理
├── release/                  # 安装包脚本
│   ├── install.bat / uninstall.bat
│   ├── FaceGuard.iss         # Inno Setup 脚本
│   ├── make_setup.bat
│   └── README_使用指南.md
├── .github/workflows/build-release.yml  # GitHub Actions 自动编译
├── build.py / requirements.txt / config.example.json
└── README.md / LICENSE
```

## 配置说明

所有配置存于 `%APPDATA%\FaceGuard\config.json`，参考 `config.example.json`。

关键项：
- `notify.password`：QQ 邮箱**授权码**（非登录密码），在 QQ 邮箱设置 → 账户 → 开启 SMTP 获取
- `recognizer.confidence_threshold`：相似度阈值，默认 0.55，越低越易通过
- `presence.absence_lock_seconds` / `sleep_after_seconds`：离开锁屏/休眠时长

## 技术说明

- **为何不用 dlib/face_recognition**：dlib 在 Windows 上需 CMake + VS Build Tools 编译，打包极易失败。改用 OpenCV DNN 的 SFace 模型，精度相当（99.55% LFW）且纯 ONNX，wheel 即装即用。
- **解锁注入**：受 Windows 安全机制限制，第三方程序无法直接"解锁"已锁桌面。FaceGuard 采用会话唤醒策略：识别到本人后唤醒显示器并触发登录画面的活体检测，配合常驻实现秒级解锁体验。

## License

MIT © Soc-Dragon
