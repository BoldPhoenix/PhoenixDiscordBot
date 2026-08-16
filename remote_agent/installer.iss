[Setup]
AppName=Phoenix ARK Agent
AppVersion=1.0.0
DefaultDirName={pf}\Phoenix ARK Agent
DefaultGroupName=Phoenix ARK Agent
OutputDir=dist
OutputBaseFilename=PhoenixArkAgentInstaller
SetupIconFile=icon.ico
WizardImageFile=wizard.bmp
WizardSmallImageFile=small.bmp
Compression=lzma2
SolidCompression=yes
PrivilegesRequired=admin

[Files]
Source: "PhoenixArkAgent.exe"; DestDir: "{app}"; Flags: ignoreversion
Source: "config.json"; DestDir: "{app}"; Flags: ignoreversion
Source: "README.txt"; DestDir: "{app}"; Flags: ignoreversion

[Dirs]
Name: "{app}\logs"

[Icons]
Name: "{group}\Phoenix ARK Agent"; Filename: "{app}\PhoenixArkAgent.exe"; Comment: "ARK Server Remote Agent"
Name: "{group}\Uninstall Phoenix ARK Agent"; Filename: "{uninstallexe}"

[Run]
Filename: "{app}\PhoenixArkAgent.exe"; Parameters: "-install"; StatusMsg: "Installing Phoenix ARK Agent service..."; Flags: runhidden

[UninstallRun]
Filename: "{app}\PhoenixArkAgent.exe"; Parameters: "-remove"; StatusMsg: "Removing Phoenix ARK Agent service..."; Flags: runhidden

[Code]
function GetCustomBoolean(Data: String): Boolean;
begin
  Result := False;
  if Data = '1' then Result := True;
  if Data = 'true' then Result := True;
  if Data = 'True' then Result := True;
  if Data = 'TRUE' then Result := True;
end;

procedure CurStepChanged(CurStep: TSetupStep);
var
  ResultCode: Integer;
begin
  if CurStep = ssPostInstall then
  begin
    // Create default config file if it doesn't exist
    if not FileExists(ExpandConstant('{app}\config.json')) then
    begin
      SaveStringToFile(ExpandConstant('{app}\config.json'), 
        '{' + #13#10 +
        '  "bot_token": "",' + #13#10 +
        '  "service_name": "PhoenixArkAgent",' + #13#10 +
        '  "port": 8080,' + #13#10 +
        '  "auth_key": "agent_' + IntToStr(GetTickCount) + '",' + #13#10 +
        '  "ark_servers": []' + #13#10 +
        '}' + #13#10);
    end;
  end;
end;

procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
begin
  if CurUninstallStep = usPostUninstall then
  begin
    // Clean up logs directory
    if DirExists(ExpandConstant('{app}\logs')) then
      DelTree(ExpandConstant('{app}\logs'), True, True, True);
  end;
end;
