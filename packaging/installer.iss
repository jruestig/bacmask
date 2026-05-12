; Inno Setup script for BioMask.
;
; Wraps the PyInstaller onefolder output at ..\dist\biomask into a single
; biomask-setup-<ver>.exe installer. Per-user install by default (no UAC);
; the user can still elevate to install machine-wide.
;
; Build:
;   1. pyinstaller packaging\biomask.spec          (produces dist\biomask\)
;   2. iscc packaging\installer.iss                (produces dist\biomask-setup-<ver>.exe)

#define MyAppName       "BioMask"
#define MyAppVersion    "0.1.0"
#define MyAppPublisher  "BioMask"
#define MyAppExeName    "biomask.exe"
#define MyAppId         "{{FE647988-ED7A-4A78-9185-D2DF9BA674DF}"

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
OutputBaseFilename=biomask-setup-{#MyAppVersion}
Compression=lzma2
SolidCompression=yes
WizardStyle=modern

; Optional branding — activated when the file exists next to this .iss.
#ifexist "biomask.ico"
SetupIconFile=biomask.ico
#endif

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "Create a &desktop shortcut"; GroupDescription: "Additional icons:"; Flags: unchecked
Name: "associate"; Description: "Associate .bmsk files with {#MyAppName}"; GroupDescription: "File associations:"; Flags: unchecked
Name: "associate_images"; Description: "Add {#MyAppName} to the 'Open with' menu for image files (.tif, .tiff, .png, .jpg, .jpeg, .bmp)"; GroupDescription: "File associations:"; Flags: unchecked

[Files]
Source: "..\dist\biomask\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{autoprograms}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Registry]
; .bmsk -> ProgID (HKA resolves to HKCU for per-user, HKLM for admin install)
Root: HKA; Subkey: "Software\Classes\.bmsk\OpenWithProgids"; ValueType: string; ValueName: "BioMask.bundle"; ValueData: ""; Flags: uninsdeletevalue; Tasks: associate
Root: HKA; Subkey: "Software\Classes\BioMask.bundle"; ValueType: string; ValueName: ""; ValueData: "BioMask bundle"; Flags: uninsdeletekey; Tasks: associate
Root: HKA; Subkey: "Software\Classes\BioMask.bundle\DefaultIcon"; ValueType: string; ValueName: ""; ValueData: "{app}\{#MyAppExeName},0"; Tasks: associate
Root: HKA; Subkey: "Software\Classes\BioMask.bundle\shell\open\command"; ValueType: string; ValueName: ""; ValueData: """{app}\{#MyAppExeName}"" ""%1"""; Tasks: associate

; Image formats -> ProgID exposed only via "Open with" — never set as the default handler.
; OpenWithProgids is the Microsoft-recommended pattern: BioMask shows up in the
; right-click "Open with" submenu without overriding the user's existing default
; viewer (Photos / IrfanView / etc.). Users can still pin BioMask as default
; themselves via "Choose another app -> Always use this app".
Root: HKA; Subkey: "Software\Classes\BioMask.image"; ValueType: string; ValueName: ""; ValueData: "Image (BioMask)"; Flags: uninsdeletekey; Tasks: associate_images
Root: HKA; Subkey: "Software\Classes\BioMask.image\DefaultIcon"; ValueType: string; ValueName: ""; ValueData: "{app}\{#MyAppExeName},0"; Tasks: associate_images
Root: HKA; Subkey: "Software\Classes\BioMask.image\shell\open\command"; ValueType: string; ValueName: ""; ValueData: """{app}\{#MyAppExeName}"" ""%1"""; Tasks: associate_images

Root: HKA; Subkey: "Software\Classes\.tif\OpenWithProgids";  ValueType: string; ValueName: "BioMask.image"; ValueData: ""; Flags: uninsdeletevalue; Tasks: associate_images
Root: HKA; Subkey: "Software\Classes\.tiff\OpenWithProgids"; ValueType: string; ValueName: "BioMask.image"; ValueData: ""; Flags: uninsdeletevalue; Tasks: associate_images
Root: HKA; Subkey: "Software\Classes\.png\OpenWithProgids";  ValueType: string; ValueName: "BioMask.image"; ValueData: ""; Flags: uninsdeletevalue; Tasks: associate_images
Root: HKA; Subkey: "Software\Classes\.jpg\OpenWithProgids";  ValueType: string; ValueName: "BioMask.image"; ValueData: ""; Flags: uninsdeletevalue; Tasks: associate_images
Root: HKA; Subkey: "Software\Classes\.jpeg\OpenWithProgids"; ValueType: string; ValueName: "BioMask.image"; ValueData: ""; Flags: uninsdeletevalue; Tasks: associate_images
Root: HKA; Subkey: "Software\Classes\.bmp\OpenWithProgids";  ValueType: string; ValueName: "BioMask.image"; ValueData: ""; Flags: uninsdeletevalue; Tasks: associate_images

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "Launch {#MyAppName}"; Flags: nowait postinstall skipifsilent

; Notes:
;   - User data at %LOCALAPPDATA%\BioMask is intentionally NOT removed on
;     uninstall — bundles + CSVs are user-generated work, not install artifacts.
;   - Double-click of a .bmsk file passes its path as argv[1]; main.py
;     routes it to MaskService.load_bundle on startup.
;   - The "Open with" image association uses OpenWithProgids only — BioMask
;     never becomes the default handler for .tif/.png/.jpg/.bmp. Users who
;     want it as default can pin it themselves via Windows' "Choose another
;     app -> Always use this app" dialog. main.py treats any non-.bmsk
;     argv[1] as an image and routes it to MaskService.load_image.
