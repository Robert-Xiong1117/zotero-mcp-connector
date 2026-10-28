; Inno Setup script — per-user install, no admin rights needed
#ifndef AppVersion
  #define AppVersion "1.0.0"
#endif
[Setup]
AppId={{6F2B1E7A-4C1D-4E8B-9C6A-2D7E5B1F0A11}
AppName=Zotero MCP
AppVersion={#AppVersion}
AppPublisher=Robert Xiong
DefaultDirName={localappdata}\Programs\ZoteroMCP
DefaultGroupName=Zotero MCP
PrivilegesRequired=lowest
OutputDir=..\dist-installer
OutputBaseFilename=ZoteroMCP-Setup-{#AppVersion}
SetupIconFile=build_assets\icon.ico
UninstallDisplayIcon={app}\ZoteroMCP.exe
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
CloseApplications=force

[Languages]
Name: "en"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"

[Files]
Source: "..\dist\ZoteroMCP\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\Zotero MCP"; Filename: "{app}\ZoteroMCP.exe"
Name: "{group}\{cm:UninstallProgram,Zotero MCP}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\Zotero MCP"; Filename: "{app}\ZoteroMCP.exe"; Tasks: desktopicon

[Run]
Filename: "{app}\ZoteroMCP.exe"; Description: "{cm:LaunchProgram,Zotero MCP}"; Flags: nowait postinstall skipifsilent

[UninstallRun]
Filename: "{sys}\taskkill.exe"; Parameters: "/F /T /IM ZoteroMCP.exe"; Flags: runhidden; RunOnceId: "KillApp"

[Registry]
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\Run"; ValueType: none; ValueName: "ZoteroMCP"; Flags: uninsdeletevalue dontcreatekey
