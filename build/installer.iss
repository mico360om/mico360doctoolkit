; Inno Setup script for MICO360 Doc Toolkit
; Build the app first:  pyinstaller build/mico360.spec --noconfirm
; Then compile this with Inno Setup 6:  iscc build\installer.iss
;
; Bundled third-party engines (Ghostscript, LibreOffice) are picked up from
; ..\vendor and installed alongside the app. See vendor\README.md.

#define AppName "MICO360 Doc Toolkit"
#define AppVersion "6.7.0"
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
; The payload is large (~1.7 GB — it bundles the LibreOffice engine). ISCC's
; LZMA compressor is 32-bit, so a single SOLID block with a big dictionary
; exhausts its address space and crashes (islzma.dll access violation). Compress
; files independently with a capped 64 MB dictionary so the 32-bit compressor
; stays well within memory. Slightly larger output, but it builds reliably.
Compression=lzma2/max
SolidCompression=no
LZMADictionarySize=65536
LZMANumBlockThreads=1
LZMAUseSeparateProcess=yes
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
; Main application (PyInstaller onedir output). This ALREADY contains the
; bundled engines under _internal\vendor\ (the spec copies vendor\ into the
; frozen app, which is where the app looks via _MEIPASS). We intentionally do
; NOT also copy ..\vendor here — that would ship LibreOffice twice and roughly
; double the installer size.
Source: "..\dist\MICO360DocToolkit\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\{#AppName}"; Filename: "{app}\{#AppExeName}"
Name: "{group}\Uninstall {#AppName}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\{#AppExeName}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#AppExeName}"; Description: "Launch {#AppName}"; Flags: nowait postinstall skipifsilent


