; Inno Setup script: builds dist\setup.exe from dist\JobAds\ (PRD §15).
; Run through build.bat. Requires Inno Setup 6 (free): https://jrsoftware.org/isinfo.php

#define AppName "JobAds"
#define AppVersion "1.0.0"
#define AppExe "JobAds.exe"

[Setup]
AppId={{6F2B8C1E-4D7A-4C3B-9E51-2A8F0D6B7C34}
AppName={#AppName}
AppVersion={#AppVersion}
AppVerName={#AppName} {#AppVersion}
; Installs for the current user only: no administrator rights needed.
PrivilegesRequired=lowest
DefaultDirName={localappdata}\{#AppName}
DisableProgramGroupPage=yes
DisableDirPage=yes
OutputDir=..\dist
OutputBaseFilename=setup
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
UninstallDisplayIcon={app}\{#AppExe}
CloseApplications=yes

[Languages]
Name: "hebrew"; MessagesFile: "compiler:Languages\Hebrew.isl"
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"

[Files]
; The program: replaced on every update.
Source: "..\dist\JobAds\*"; DestDir: "{app}"; Flags: recursesubdirs createallsubdirs ignoreversion
; The user's files: installed only if missing, so updates never overwrite them.
; config.default.json: the settings a new user starts with (no distribution group yet; the user sets it in the menu).
Source: "config.default.json"; DestDir: "{app}"; DestName: "config.json"; Flags: onlyifdoesntexist uninsneveruninstall
Source: "..\api_key.json"; DestDir: "{app}"; Flags: onlyifdoesntexist uninsneveruninstall
Source: "..\communities\*"; DestDir: "{app}\communities"; Flags: recursesubdirs createallsubdirs onlyifdoesntexist uninsneveruninstall

[Icons]
Name: "{userprograms}\{#AppName}"; Filename: "{app}\{#AppExe}"
Name: "{userdesktop}\{#AppName}"; Filename: "{app}\{#AppExe}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#AppExe}"; Description: "{cm:LaunchProgram,{#AppName}}"; Flags: nowait postinstall skipifsilent

[UninstallDelete]
Type: filesandordirs; Name: "{app}\logs"

[Code]
procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
begin
  if CurUninstallStep = usPostUninstall then
  begin
    { SuppressibleMsgBox: in a silent uninstall it answers IDNO, so the data is kept. }
    if SuppressibleMsgBox('למחוק גם את הנתונים?' + #13#10 +
              'מסד המודעות, ההגדרות, מפתח ה-API, קבצי הקהילות וההתחברות לפייסבוק ולווטסאפ.' + #13#10 + #13#10 +
              'לחצו "לא" כדי לשמור אותם להתקנה הבאה.',
              mbConfirmation, MB_YESNO or MB_DEFBUTTON2, IDNO) = IDYES then
      DelTree(ExpandConstant('{app}'), True, True, True);
  end;
end;
