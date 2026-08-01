; FaceGuard Inno Setup 脚本
; 用 Inno Setup 编译本文件生成 FaceGuard-Setup.exe
; 命令行编译：iscc.exe release\FaceGuard.iss

#define MyAppName "FaceGuard"
#define MyAppVersion "2.2.0"
#define MyAppPublisher "Soc-Dragon"
#define MyAppExeName "FaceGuard.exe"
#define MyAppURL "https://github.com/Soc-Dragon/FaceGuard"

[Setup]
AppId={{B7F3A2E1-9C4D-4E6B-8A1F-3D5E7F9C2A01}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppVerName={#MyAppName} {#MyAppVersion}
AppPublisher={#MyAppPublisher}
AppPublisherURL={#MyAppURL}
AppSupportURL={#MyAppURL}
AppUpdatesURL={#MyAppURL}
DefaultDirName={autopf}\{#MyAppName}
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=yes
OutputDir=..\dist_setup
OutputBaseFilename=FaceGuard-Setup
Compression=lzma2/ultra64
SolidCompression=yes
ArchitecturesAllowed=x64
ArchitecturesInstallIn64BitMode=x64
WizardStyle=modern
PrivilegesRequired=admin
UninstallDisplayIcon={app}\{#MyAppExeName}

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "创建桌面快捷方式"; GroupDescription: "附加选项:"; Flags: unchecked

[Files]
; 主程序（PyInstaller 产物）
Source: "..\dist\FaceGuard.exe"; DestDir: "{app}"; Flags: ignoreversion
; 配置示例与文档
Source: "..\config.example.json"; DestDir: "{app}"; Flags: ignoreversion
Source: "README_使用指南.md"; DestDir: "{app}"; Flags: ignoreversion
Source: "install.bat"; DestDir: "{app}"; Flags: ignoreversion
Source: "uninstall.bat"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{group}\FaceGuard"; Filename: "{app}\{#MyAppExeName}"
Name: "{group}\FaceGuard 注册人脸"; Filename: "{app}\{#MyAppExeName}"; Parameters: "--enroll"
Name: "{group}\FaceGuard 设置"; Filename: "{app}\{#MyAppExeName}"; Parameters: "--config"
Name: "{group}\卸载 FaceGuard"; Filename: "{uninstallexe}"
Name: "{commondesktop}\FaceGuard"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Run]
; 安装后写入注册表自启项（自启用 --silent，开机后台常驻）
Filename: "{app}\install.bat"; Flags: runhidden waituntilterminated
; 安装完成后引导首次注册（强制弹出，不跳过）
Filename: "{app}\{#MyAppExeName}"; Parameters: "--enroll"; Description: "立即注册人脸"; Flags: postinstall skipifsilent

[UninstallRun]
Filename: "{app}\uninstall.bat"; Flags: runhidden waituntilterminated

[UninstallDelete]
Type: filesandordirs; Name: "{app}"
