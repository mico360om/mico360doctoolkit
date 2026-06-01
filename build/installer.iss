; Inno Setup script for MICO360 Doc Toolkit
; Build the app first:  pyinstaller build/mico360.spec --noconfirm
; Then compile this with Inno Setup 6:  iscc build\installer.iss
;
; Bundled third-party engines (Ghostscript, LibreOffice) are picked up from
; ..\vendor and installed alongside the app. See vendor\README.md.

#define AppName "MICO360 Doc Toolkit"
#define AppVersion "5.4.0"
#define AppPublisher "MICO360"
#define AppExeName "MICO360DocToolkit.exe"

[Setup]
AppId={{8E5C2A41-9F3B-4D8E-AB12-CD34EF567890}}
AppName={#AppName}
AppVersion={#AppVersion}
AppPublisher={#AppPublisher}
DefaultDirName={autopf}\MICO360\Doc Toolkit
DefaultGroupName=MICO360 Doc Toolkit
DisableProgramGroupPage=yes
OutputDir=..\dist\installer
OutputBaseFilename=MICO360-DocToolkit-Setup-{#AppVersion}
SetupIconFile=..\mico360\resources\app.ico
UninstallDisplayIcon={app}\{#AppExeName}
Compression=lzma2/max
SolidCompression=yes
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
WizardStyle=modern
PrivilegesRequired=admin
MinVersion=10.0
; Auto-update support: close the running app during an in-place upgrade and
; restart it afterwards (the updater launches Setup with /CLOSEAPPLICATIONS).
CloseApplications=yes
RestartApplications=yes

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "Create a &desktop shortcut"; GroupDescription: "Additional icons:"

[Files]
; Main application (PyInstaller onedir output)
Source: "..\dist\MICO360DocToolkit\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
; Bundled engines (optional - only included if present at build time)
Source: "..\vendor\*"; DestDir: "{app}\vendor"; Flags: ignoreversion recursesubdirs createallsubdirs skipifsourcedoesntexist

[Icons]
Name: "{group}\{#AppName}"; Filename: "{app}\{#AppExeName}"
Name: "{group}\Uninstall {#AppName}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\{#AppExeName}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#AppExeName}"; Description: "Launch {#AppName}"; Flags: nowait postinstall skipifsilent


