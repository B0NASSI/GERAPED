#define MyAppName "GERAPED — Gerador de Pedidos"
#define MyAppVersion "1.3.0"
#define MyAppPublisher "Rodriguez & Sousa Advogados Associados"
#define MyAppExeName "GERAPED Launcher.exe"
#define SourceDir "C:\Users\Pichau\Desktop\CODE\CLAUDE CODE\GeradorPedidoFAP\GERAPED - Instalador"

[Setup]
AppId={{9C4E2A7D-1F6B-4A3C-8E5D-2B7F0C9A4D6E}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
AppVerName={#MyAppName} {#MyAppVersion}
DefaultDirName={localappdata}\GERAPED
DefaultGroupName=GERAPED
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
ArchitecturesInstallIn64BitMode=x64compatible
OutputDir=output
OutputBaseFilename=GERAPED Setup v{#MyAppVersion}
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
UninstallDisplayName={#MyAppName}
UninstallDisplayIcon={app}\{#MyAppExeName}
DisableWelcomePage=no

[Languages]
Name: "brazilianportuguese"; MessagesFile: "compiler:Languages\BrazilianPortuguese.isl"

[Tasks]
Name: "desktopicon"; Description: "Criar um atalho na área de trabalho"; GroupDescription: "Atalhos adicionais:"

[Files]
Source: "{#SourceDir}\GERAPED.exe"; DestDir: "{app}"; Flags: ignoreversion
Source: "{#SourceDir}\_internal\*"; DestDir: "{app}\_internal"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "{#SourceDir}\GERAPED Launcher.exe"; DestDir: "{app}"; Flags: ignoreversion
Source: "{#SourceDir}\_internal_launcher\*"; DestDir: "{app}\_internal_launcher"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "{#SourceDir}\versao.txt"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{autodesktop}\GERAPED"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[UninstallDelete]
Type: filesandordirs; Name: "{app}"

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "Abrir o GERAPED agora"; Flags: nowait postinstall skipifsilent
