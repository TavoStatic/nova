#define AppName "NYO System"
#define AppPublisher "NYO System"
#define AppVersion GetEnv("NYO_APP_VERSION")
#define PayloadDir GetEnv("NYO_PAYLOAD_DIR")
#define InstallerOutputDir GetEnv("NYO_INSTALLER_OUTPUT_DIR")

#if "{#PayloadDir}" == ""
  #error NYO_PAYLOAD_DIR must point at an extracted NYO System package payload before compiling the installer.
#endif

#if "{#AppVersion}" == ""
  #define AppVersion "0.0.0-dev"
#endif

#if "{#InstallerOutputDir}" == ""
  #define InstallerOutputDir "."
#endif

[Setup]
AppId={{1C6299E2-B2DB-45CB-8F90-87F4253D55D0}
AppName={#AppName}
AppVersion={#AppVersion}
AppPublisher={#AppPublisher}
DefaultDirName={autopf}\NYO System
DefaultGroupName=NYO System
DisableProgramGroupPage=yes
OutputDir={#InstallerOutputDir}
OutputBaseFilename=nyo-system-installer-{#AppVersion}
Compression=lzma
SolidCompression=yes
WizardStyle=modern
PrivilegesRequired=admin
PrivilegesRequiredOverridesAllowed=commandline
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
UninstallDisplayIcon={app}\nova.cmd

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "route_guided"; Description: "Install route: recommended guided setup"; Flags: exclusive checkedonce
Name: "route_baseonly"; Description: "Install route: base package only"; Flags: exclusive
Name: "route_manual"; Description: "Install route: manual / advanced setup"; Flags: exclusive
Name: "desktopicon"; Description: "Create a desktop shortcut"; Flags: unchecked

[Files]
Source: "{#PayloadDir}\*"; DestDir: "{app}"; Flags: recursesubdirs createallsubdirs ignoreversion

[Icons]
Name: "{group}\NYO System Shell"; Filename: "{app}\nova.cmd"; WorkingDir: "{app}"
Name: "{group}\NYO System Control"; Filename: "{app}\nova.cmd"; Parameters: "webui-start --host 127.0.0.1 --port 8080"; WorkingDir: "{app}"
Name: "{group}\NYO System Logs"; Filename: "{cmd}"; Parameters: "/C start "" ""{app}\logs"""; WorkingDir: "{app}"
Name: "{commondesktop}\NYO System Shell"; Filename: "{app}\nova.cmd"; WorkingDir: "{app}"; Tasks: desktopicon

[Run]
Filename: "powershell.exe"; Parameters: "-NoProfile -ExecutionPolicy Bypass -File ""{app}\scripts\installer_hardware_check.ps1"""; StatusMsg: "Checking hardware and environment readiness..."; Flags: postinstall waituntilterminated runhidden
Filename: "{app}\nova.cmd"; Parameters: "install"; WorkingDir: "{app}"; StatusMsg: "Bootstrapping NYO System environment..."; Flags: postinstall waituntilterminated; Tasks: route_guided
Filename: "{app}\nova.cmd"; Parameters: "doctor"; WorkingDir: "{app}"; StatusMsg: "Running NYO System doctor..."; Flags: postinstall waituntilterminated; Tasks: route_guided
Filename: "{app}\nova.cmd"; Parameters: "runtime-status"; WorkingDir: "{app}"; StatusMsg: "Collecting runtime readiness status..."; Flags: postinstall waituntilterminated; Tasks: route_guided

[Code]
function InitializeSetup(): Boolean;
begin
  Result := True;
end;

procedure CurPageChanged(CurPageID: Integer);
begin
  if CurPageID = wpSelectTasks then
  begin
    WizardForm.TasksList.Hint :=
      'Choose one install route. ' +
      'Recommended guided setup runs nova install, doctor, and runtime-status automatically. ' +
      'Base package only copies files and runs the readiness check. ' +
      'Manual setup copies files and leaves bootstrap to the operator.';
  end;
end;
