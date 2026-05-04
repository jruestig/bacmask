; Inno Setup script for BacMask.
;
; Wraps the PyInstaller onefolder output at ..\dist\bacmask into a single
; bacmask-setup-<ver>.exe installer. Per-user install by default (no UAC);
; the user can still elevate to install machine-wide.
;
; Build:
;   1. pyinstaller packaging\bacmask.spec          (produces dist\bacmask\)
;   2. iscc packaging\installer.iss                (produces dist\bacmask-setup-<ver>.exe)

#define MyAppName       "BacMask"
#define MyAppVersion    "0.0.9"
#define MyAppPublisher  "BacMask"
#define MyAppExeName    "bacmask.exe"
#define MyAppId         "{{A0F3C2B4-6D8E-4F12-9E3C-1B2A4D5E6F70}"

[Setup]
AppId={#MyAppId}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
VersionInfoVersion={#MyAppVersion}

; Per-user by default, user can opt into machine-wide via the dialog.
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog

DefaultDirName={autopf}\{#MyAppName}
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=yes
UninstallDisplayIcon={app}\{#MyAppExeName}
UninstallDisplayName={#MyAppName} {#MyAppVersion}

; x64 only — matches PyInstaller build architecture.
ArchitecturesAllowed=x64
ArchitecturesInstallIn64BitMode=x64

OutputDir=..\dist
OutputBaseFilename=bacmask-setup-{#MyAppVersion}
Compression=lzma2
SolidCompression=yes
WizardStyle=modern

; Optional branding — activated when the file exists next to this .iss.
#ifexist "bacmask.ico"
SetupIconFile=bacmask.ico
#endif

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "Create a &desktop shortcut"; GroupDescription: "Additional icons:"; Flags: unchecked
Name: "associate"; Description: "Associate .bacmask files with {#MyAppName}"; GroupDescription: "File associations:"; Flags: unchecked
Name: "associate_images"; Description: "Add {#MyAppName} to the 'Open with' menu for image files (.tif, .tiff, .png, .jpg, .jpeg, .bmp)"; GroupDescription: "File associations:"; Flags: unchecked

[Files]
Source: "..\dist\bacmask\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{autoprograms}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Registry]
; .bacmask -> ProgID (HKA resolves to HKCU for per-user, HKLM for admin install)
Root: HKA; Subkey: "Software\Classes\.bacmask\OpenWithProgids"; ValueType: string; ValueName: "BacMask.bundle"; ValueData: ""; Flags: uninsdeletevalue; Tasks: associate
Root: HKA; Subkey: "Software\Classes\BacMask.bundle"; ValueType: string; ValueName: ""; ValueData: "BacMask bundle"; Flags: uninsdeletekey; Tasks: associate
Root: HKA; Subkey: "Software\Classes\BacMask.bundle\DefaultIcon"; ValueType: string; ValueName: ""; ValueData: "{app}\{#MyAppExeName},0"; Tasks: associate
Root: HKA; Subkey: "Software\Classes\BacMask.bundle\shell\open\command"; ValueType: string; ValueName: ""; ValueData: """{app}\{#MyAppExeName}"" ""%1"""; Tasks: associate

; Image formats -> ProgID exposed only via "Open with" — never set as the default handler.
; OpenWithProgids is the Microsoft-recommended pattern: BacMask shows up in the
; right-click "Open with" submenu without overriding the user's existing default
; viewer (Photos / IrfanView / etc.). Users can still pin BacMask as default
; themselves via "Choose another app -> Always use this app".
Root: HKA; Subkey: "Software\Classes\BacMask.image"; ValueType: string; ValueName: ""; ValueData: "Image (BacMask)"; Flags: uninsdeletekey; Tasks: associate_images
Root: HKA; Subkey: "Software\Classes\BacMask.image\DefaultIcon"; ValueType: string; ValueName: ""; ValueData: "{app}\{#MyAppExeName},0"; Tasks: associate_images
Root: HKA; Subkey: "Software\Classes\BacMask.image\shell\open\command"; ValueType: string; ValueName: ""; ValueData: """{app}\{#MyAppExeName}"" ""%1"""; Tasks: associate_images

Root: HKA; Subkey: "Software\Classes\.tif\OpenWithProgids";  ValueType: string; ValueName: "BacMask.image"; ValueData: ""; Flags: uninsdeletevalue; Tasks: associate_images
Root: HKA; Subkey: "Software\Classes\.tiff\OpenWithProgids"; ValueType: string; ValueName: "BacMask.image"; ValueData: ""; Flags: uninsdeletevalue; Tasks: associate_images
Root: HKA; Subkey: "Software\Classes\.png\OpenWithProgids";  ValueType: string; ValueName: "BacMask.image"; ValueData: ""; Flags: uninsdeletevalue; Tasks: associate_images
Root: HKA; Subkey: "Software\Classes\.jpg\OpenWithProgids";  ValueType: string; ValueName: "BacMask.image"; ValueData: ""; Flags: uninsdeletevalue; Tasks: associate_images
Root: HKA; Subkey: "Software\Classes\.jpeg\OpenWithProgids"; ValueType: string; ValueName: "BacMask.image"; ValueData: ""; Flags: uninsdeletevalue; Tasks: associate_images
Root: HKA; Subkey: "Software\Classes\.bmp\OpenWithProgids";  ValueType: string; ValueName: "BacMask.image"; ValueData: ""; Flags: uninsdeletevalue; Tasks: associate_images

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "Launch {#MyAppName}"; Flags: nowait postinstall skipifsilent

; Notes:
;   - User data at %LOCALAPPDATA%\BacMask is intentionally NOT removed on
;     uninstall — bundles + CSVs are user-generated work, not install artifacts.
;   - Double-click of a .bacmask file passes its path as argv[1]; main.py
;     routes it to MaskService.load_bundle on startup.
;   - The "Open with" image association uses OpenWithProgids only — BacMask
;     never becomes the default handler for .tif/.png/.jpg/.bmp. Users who
;     want it as default can pin it themselves via Windows' "Choose another
;     app -> Always use this app" dialog. main.py treats any non-.bacmask
;     argv[1] as an image and routes it to MaskService.load_image.
