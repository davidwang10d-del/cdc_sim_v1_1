; Inno Setup 6 definition. Values are supplied by build_release.ps1.

#ifndef AppVersion
  #define AppVersion "0.0.0-local"
#endif
#ifndef WindowsVersion
  #define WindowsVersion "0.0.0.0"
#endif
#ifndef AppPublisher
  #define AppPublisher "CDC Sim"
#endif
#ifndef SourceDir
  #error SourceDir must identify the validated release stage
#endif
#ifndef OutputDir
  #error OutputDir must identify the installer output directory
#endif
#ifndef LicensePath
  #error LicensePath must identify the reviewed distribution license
#endif

[Setup]
AppId={{8B99B15E-3B3B-48F5-A4CD-66E26B274AD4}
AppName=CDC Sim
AppVersion={#AppVersion}
AppPublisher={#AppPublisher}
AppMutex=Local\CDC-Sim-Private-Beta
VersionInfoVersion={#WindowsVersion}
VersionInfoCompany={#AppPublisher}
VersionInfoDescription=CDC Sim private beta installer
VersionInfoProductName=CDC Sim
DefaultDirName={localappdata}\Programs\CDC Sim
DefaultGroupName=CDC Sim
UninstallDisplayIcon={app}\CDC Sim.exe
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
MinVersion=10.0.19045
OutputDir={#OutputDir}
OutputBaseFilename=CDC-Sim-Setup-{#AppVersion}-win-x64
Compression=lzma2/ultra64
SolidCompression=yes
WizardStyle=modern
LicenseFile={#LicensePath}
CloseApplications=yes
RestartApplications=no
DisableProgramGroupPage=yes
SetupLogging=yes

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "Create a desktop shortcut"; GroupDescription: "Shortcuts:"; Flags: checkedonce

[Files]
Source: "{#SourceDir}\bundle\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "{#SourceDir}\release-manifest.json"; DestDir: "{app}\release"; Flags: ignoreversion
Source: "{#SourceDir}\dependency-inventory.json"; DestDir: "{app}\release"; Flags: ignoreversion
Source: "{#SourceDir}\BETA-TESTER-README.txt"; DestDir: "{app}"; Flags: ignoreversion isreadme
Source: "{#SourceDir}\private-beta-config.example.json"; DestDir: "{app}\release"; Flags: ignoreversion
Source: "{#SourceDir}\EULA.txt"; DestDir: "{app}"; Flags: ignoreversion
Source: "{#SourceDir}\bundle\_internal\THIRD-PARTY-NOTICES.txt"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{autoprograms}\CDC Sim"; Filename: "{app}\CDC Sim.exe"; WorkingDir: "{app}"
Name: "{autodesktop}\CDC Sim"; Filename: "{app}\CDC Sim.exe"; WorkingDir: "{app}"; Tasks: desktopicon

[Run]
Filename: "{app}\CDC Sim.exe"; Description: "Launch CDC Sim"; Flags: nowait postinstall skipifsilent
