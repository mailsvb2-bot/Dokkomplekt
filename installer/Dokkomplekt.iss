#define MyAppName "Dokkomplekt"
#define MyAppVersion "1.4.92"
#define MyAppExeName "MedicalDiaryAutofill.exe"

[Setup]
AppId={{1BA4CB75-4A83-4E09-A122-7D5619078D91}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher=Dokkomplekt
DefaultDirName={localappdata}\Dokkomplekt
DefaultGroupName=Dokkomplekt
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
OutputDir=..\dist
OutputBaseFilename=Dokkomplekt-Setup-{#MyAppVersion}
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
CloseApplications=force
RestartApplications=no
UninstallDisplayIcon={app}\{#MyAppExeName}
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
SetupLogging=yes

[Files]
Source: "..\dist\{#MyAppExeName}"; DestDir: "{app}"; Flags: ignoreversion

[Dirs]
Name: "{userdesktop}\Выписанные пациенты"

[Icons]
Name: "{group}\Dokkomplekt"; Filename: "{app}\{#MyAppExeName}"
Name: "{autodesktop}\Dokkomplekt"; Filename: "{app}\{#MyAppExeName}"

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "Запустить Dokkomplekt"; Flags: nowait postinstall skipifsilent

[UninstallDelete]
Type: files; Name: "{autostartup}\MedicalDiaryAutofill Intake Agent.vbs"
Type: files; Name: "{autostartup}\MedicalDiaryAutofill Intake Agent.lnk"
Type: files; Name: "{userappdata}\MedicalDiaryAutofill\desktop_intake_agent.lock"
Type: files; Name: "{userappdata}\MedicalDiaryAutofill\desktop_intake_agent_handoff.json"

[Code]
function InitializeUninstall(): Boolean;
var
  ResultCode: Integer;
  AppExe: String;
begin
  Result := True;
  AppExe := ExpandConstant('{app}\{#MyAppExeName}');
  if FileExists(AppExe) then
  begin
    if (not Exec(AppExe, '--uninstall-intake-agent', ExpandConstant('{app}'), SW_HIDE, ewWaitUntilTerminated, ResultCode)) or (ResultCode <> 0) then
    begin
      SuppressibleMsgBox('Не удалось безопасно завершить Dokkomplekt. Закройте программу и повторите удаление.', mbError, MB_OK, IDOK);
      Result := False;
    end;
  end;
end;
