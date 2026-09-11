; AIDSE Desktop — Inno Setup Installer Script
; Produces a single-file Windows installer (.exe) for distribution from website

#define MyAppName "AIDSE Desktop"
#define MyAppVersion "0.1.0"
#define MyAppPublisher "AIDSE Platform"
#define MyAppURL "https://aidse.app"
#define MyAppExeName "Launch-AIDSE.vbs"

[Setup]
AppId={{D37B4391-7C4E-4B0D-9E9C-3382F992E21D}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
AppPublisherURL={#MyAppURL}
AppSupportURL={#MyAppURL}
AppUpdatesURL={#MyAppURL}
DefaultDirName={autopf}\{#MyAppName}
DisableProgramGroupPage=yes
LicenseFile=src-tauri\LICENSE.txt
OutputDir=dist-installer
OutputBaseFilename=AIDSE-Platform_0.1.0_x64-setup
SetupIconFile=src-tauri\icons\icon.ico
Compression=lzma2/ultra64
SolidCompression=yes
WizardStyle=modern
PrivilegesRequired=lowest
CloseApplications=yes

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"

[Files]
; Standalone compiled Python/ML backend
Source: "dist\aidse-backend\*"; DestDir: "{app}\dist\aidse-backend"; Flags: ignoreversion recursesubdirs createallsubdirs
; Static Next.js frontend export
Source: "apps\web\out\*"; DestDir: "{app}\apps\web\out"; Flags: ignoreversion recursesubdirs createallsubdirs
; Python API source
Source: "apps\api\*"; DestDir: "{app}\apps\api"; Flags: ignoreversion recursesubdirs createallsubdirs
; Alembic config. The migration runner resolves this next to apps/, so without
; it run_migrations_headless() finds nothing and returns — which is how every
; installed copy ended up with a create_all schema and no alembic_version row.
Source: "alembic.ini"; DestDir: "{app}"; Flags: ignoreversion
; Launchers & Icons
Source: "Launch-AIDSE.vbs"; DestDir: "{app}"; Flags: ignoreversion
Source: "Launch-AIDSE.bat"; DestDir: "{app}"; Flags: ignoreversion
Source: "src-tauri\icons\icon.ico"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{autoprograms}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; IconFilename: "{app}\icon.ico"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; IconFilename: "{app}\icon.ico"; Tasks: desktopicon

[UninstallDelete]
Type: filesandordirs; Name: "{localappdata}\AIDSE-Desktop"

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "{cm:LaunchProgram,{#StringChange(MyAppName, '&', '&&')}}"; Flags: shellexec postinstall skipifsilent
