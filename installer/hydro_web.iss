#ifndef MyAppVersion
  #define MyAppVersion "2.4.0"
#endif

[Setup]
AppId={{D6B4F8E2-3B51-4F7A-9C89-6F9C1E8B4B11}
AppName=HYDRO Web
AppVersion={#MyAppVersion}
AppVerName=HYDRO Web v{#MyAppVersion}
AppPublisher=HYDRO - Hidrostatik Test Degerlendirme
DefaultDirName={autopf}\HYDRO Web
DefaultGroupName=HYDRO Web
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog commandline
OutputDir=..\release
OutputBaseFilename=HydroWeb-v{#MyAppVersion}-windows-x64-setup
Compression=lzma2/normal
SolidCompression=yes
WizardStyle=modern
SetupIconFile=..\assets\icons\hydro.ico
UninstallDisplayIcon={app}\HydroWeb.exe
#if VER >= EncodeVer(6,3,0)
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
#else
ArchitecturesAllowed=x64
ArchitecturesInstallIn64BitMode=x64
#endif

[Languages]
#if FileExists(AddBackslash(CompilerPath) + "Languages\Turkish.isl")
Name: "turkish"; MessagesFile: "compiler:Languages\Turkish.isl"
#endif
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: checkedonce

[Files]
Source: "..\dist\HydroWeb\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{autoprograms}\HYDRO Web"; Filename: "{app}\HydroWeb.exe"
Name: "{autodesktop}\HYDRO Web"; Filename: "{app}\HydroWeb.exe"; Tasks: desktopicon

[Run]
Filename: "{app}\HydroWeb.exe"; Description: "{cm:LaunchProgram,HYDRO Web}"; Flags: nowait postinstall skipifsilent
