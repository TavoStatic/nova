#define AppName "Nova"
#define AppPublisher "Nova"
#define AppVersion GetEnv("Nova_APP_VERSION")
#define PayloadDir GetEnv("Nova_PAYLOAD_DIR")
#define InstallerOutputDir GetEnv("Nova_INSTALLER_OUTPUT_DIR")

#if "{#PayloadDir}" == ""
  #error Nova_PAYLOAD_DIR must point at an extracted Nova package payload before compiling the installer.
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
DefaultDirName={autopf}\Nova
DefaultGroupName=Nova
DisableProgramGroupPage=yes
OutputDir={#InstallerOutputDir}
OutputBaseFilename=nova-installer-{#AppVersion}
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
Name: "route_guided"; Description: "Install route: recommended guided setup (verify, bootstrap, runtime check)"; Flags: exclusive checkedonce
Name: "route_baseonly"; Description: "Install route: base runtime bootstrap (verify, bootstrap, smoke check)"; Flags: exclusive
Name: "route_manual"; Description: "Install route: manual / advanced setup (copy files only)"; Flags: exclusive
Name: "desktopicon"; Description: "Create a desktop shortcut"; Flags: unchecked

[Files]
Source: "{#PayloadDir}\*"; DestDir: "{app}"; Flags: recursesubdirs createallsubdirs ignoreversion

[Icons]
Name: "{group}\Nova Shell"; Filename: "{app}\nova.cmd"; WorkingDir: "{app}"
Name: "{group}\Nova Control"; Filename: "{app}\nova.cmd"; Parameters: "webui-start --host 127.0.0.1 --port 8080"; WorkingDir: "{app}"
Name: "{group}\Nova Logs"; Filename: "{cmd}"; Parameters: "/C start "" ""{app}\logs"""; WorkingDir: "{app}"
Name: "{commondesktop}\Nova Shell"; Filename: "{app}\nova.cmd"; WorkingDir: "{app}"; Tasks: desktopicon

[Run]
Filename: "powershell.exe"; Parameters: "-NoProfile -ExecutionPolicy Bypass -File ""{app}\scripts\installer_hardware_check.ps1"""; StatusMsg: "Checking hardware and environment readiness..."; Flags: postinstall waituntilterminated runhidden
Filename: "{app}\nova.cmd"; Parameters: "package-verify ."; WorkingDir: "{app}"; StatusMsg: "Verifying Nova package payload..."; Flags: postinstall waituntilterminated; Tasks: route_guided route_baseonly
Filename: "{app}\nova.cmd"; Parameters: "install"; WorkingDir: "{app}"; StatusMsg: "Bootstrapping Nova environment..."; Flags: postinstall waituntilterminated; Tasks: route_guided route_baseonly
Filename: "{app}\nova.cmd"; Parameters: "runtime-status"; WorkingDir: "{app}"; StatusMsg: "Collecting runtime readiness status..."; Flags: postinstall waituntilterminated; Tasks: route_guided
Filename: "{app}\nova.cmd"; Parameters: "smoke-base --fix"; WorkingDir: "{app}"; StatusMsg: "Running Nova base smoke check..."; Flags: postinstall waituntilterminated; Tasks: route_guided route_baseonly

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
      'Recommended guided setup runs package verify, bootstrap install, runtime-status, and smoke-base automatically. ' +
      'Base runtime bootstrap runs package verify, bootstrap install, and smoke-base automatically. ' +
      'Manual setup copies files and leaves bootstrap to the operator.';
  end;
end;
