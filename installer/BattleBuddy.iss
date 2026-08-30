; Battle Buddy per-user installer. No admin. No account.
; PrivilegesRequired=lowest. State stays in %USERPROFILE%\.battlebuddy.

#ifndef MyAppVersion
#define MyAppVersion "1.0.0"
#endif

#define MyAppName "Battle Buddy"
#define MyAppExeName "BattleBuddy.exe"

[Setup]
AppId={{8F3A2C1D-6B47-4E90-A1D5-7C9E2F4B8A31}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppVerName={#MyAppName} {#MyAppVersion}
AppPublisher=Captain Phyre
AppPublisherURL=https://github.com/wyldephyre/battle-buddy
AppSupportURL=https://github.com/wyldephyre/battle-buddy
DefaultDirName={localappdata}\BattleBuddy
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
OutputDir=..\dist
OutputBaseFilename=BattleBuddy-Setup
Compression=lzma
SolidCompression=yes
WizardStyle=modern
UninstallDisplayName={#MyAppName}
Uninstallable=yes
CloseApplications=yes
; No login. No Steam. No cloud key.

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "Desktop shortcut"; GroupDescription: "Shortcuts:"; Flags: checkedonce

[Files]
; llm\ (llama-server + GGUF) rides along if build-windows.ps1 dropped it. No login.
Source: "..\dist\BattleBuddy\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{autodesktop}\Battle Buddy"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon
Name: "{autoprograms}\Battle Buddy"; Filename: "{app}\{#MyAppExeName}"

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "Launch Battle Buddy"; Flags: nowait postinstall skipifsilent
