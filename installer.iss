; Inno Setup script for Playlist Adder. Built by build.ps1 after PyInstaller has filled dist\PlaylistAdder.

#define AppName "Playlist Adder"
#define AppVersion "1.0.0"
#define AppExe "PlaylistAdder.exe"
; build.ps1 passes a short staging path: Inno Setup can't read files past the 260-character path limit.
#ifndef SourceDir
  #define SourceDir "dist\PlaylistAdder"
#endif

[Setup]
AppId={{8F2C7A31-5B6E-4E0B-9C1D-2A7F3E4B5C6D}
AppName={#AppName}
AppVersion={#AppVersion}
AppVerName={#AppName} {#AppVersion}
; Per-user install into %LOCALAPPDATA%\Programs: no admin prompt.
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog
DefaultDirName={autopf}\{#AppName}
DefaultGroupName={#AppName}
DisableProgramGroupPage=yes
OutputDir=dist
OutputBaseFilename=PlaylistAdder-Setup
SetupIconFile=icon.ico
UninstallDisplayIcon={app}\{#AppExe}
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"

[Files]
Source: "{#SourceDir}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\{#AppName}"; Filename: "{app}\{#AppExe}"
Name: "{group}\Uninstall {#AppName}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\{#AppExe}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#AppExe}"; Description: "{cm:LaunchProgram,{#AppName}}"; Flags: nowait postinstall skipifsilent

[UninstallDelete]
; The screen pictures captured by the app live here (see default_templates_dir).
Type: filesandordirs; Name: "{localappdata}\PlaylistAdder"
