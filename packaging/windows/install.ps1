param([switch]$NoLaunch)
$ErrorActionPreference = 'Stop'
$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot '../..')).Path
$dotnetCommand = Get-Command dotnet -ErrorAction SilentlyContinue
$dotnet = if ($dotnetCommand) { $dotnetCommand.Source } else { Join-Path $env:LOCALAPPDATA 'Microsoft/dotnet/dotnet.exe' }
if (!(Test-Path -LiteralPath $dotnet)) {
    $installer = Join-Path $env:TEMP 'antigravity-supervisor-dotnet-install.ps1'
    Invoke-WebRequest 'https://dot.net/v1/dotnet-install.ps1' -OutFile $installer
    & $installer -Channel 10.0 -InstallDir (Join-Path $env:LOCALAPPDATA 'Microsoft/dotnet') -NoPath
    if ($LASTEXITCODE -ne 0) { throw 'Failed to install .NET SDK' }
}
$python = (Get-Command python -ErrorAction Stop).Source
& $python -c 'import sys; assert sys.version_info >= (3,10), "Python 3.10+ required"'
if ($LASTEXITCODE -ne 0) { throw 'Python 3.10+ required' }
$installRoot = Join-Path $env:LOCALAPPDATA 'Programs/AntigravityUsageSupervisor'
if (Get-Process AntigravityUsageSupervisor -ErrorAction SilentlyContinue) { throw 'Please exit Antigravity Usage Supervisor before reinstalling.' }
$architecture = [System.Runtime.InteropServices.RuntimeInformation]::OSArchitecture
$runtime = switch ($architecture) {
    'X64' { 'win-x64' }
    'Arm64' { 'win-arm64' }
    default { throw 'Windows x64 or ARM64 is required.' }
}
$agy = Join-Path $env:LOCALAPPDATA 'agy/bin/agy.exe'
if (!(Test-Path -LiteralPath $agy) -and !(Get-Command agy.exe -ErrorAction SilentlyContinue)) {
    $agyInstaller = Join-Path $env:TEMP ('antigravity-cli-' + [Guid]::NewGuid() + '.ps1')
    try {
        Invoke-WebRequest -UseBasicParsing 'https://antigravity.google/cli/install.ps1' -OutFile $agyInstaller
        powershell.exe -NoProfile -ExecutionPolicy Bypass -File $agyInstaller
        if ($LASTEXITCODE -ne 0 -or !(Test-Path -LiteralPath $agy)) { throw 'Antigravity CLI installation failed.' }
    }
    finally {
        if (Test-Path -LiteralPath $agyInstaller) { Remove-Item -LiteralPath $agyInstaller }
    }
}
& $dotnet publish (Join-Path $repoRoot 'windows/AntigravityUsageSupervisor/AntigravityUsageSupervisor.csproj') -c Release -r $runtime --self-contained true -o $installRoot
if ($LASTEXITCODE -ne 0) { throw 'Windows build failed' }
$backend = Join-Path $installRoot 'backend/antigravity_usage_supervisor'
New-Item -ItemType Directory -Force $backend | Out-Null
Get-ChildItem -LiteralPath (Join-Path $repoRoot 'src/antigravity_usage_supervisor') -Filter '*.py' -File |
    Copy-Item -Destination $backend -Force
@{ python = $python } | ConvertTo-Json | Set-Content -Encoding utf8 (Join-Path $installRoot 'backend.json')
$shell = New-Object -ComObject WScript.Shell
$shortcut = $shell.CreateShortcut((Join-Path ([Environment]::GetFolderPath('Desktop')) 'Antigravity Usage Supervisor.lnk'))
$shortcut.TargetPath = Join-Path $installRoot 'AntigravityUsageSupervisor.exe'
$shortcut.WorkingDirectory = $installRoot
$shortcut.Save()
$startMenu = Join-Path ([Environment]::GetFolderPath('StartMenu')) 'Programs/Antigravity Usage Supervisor.lnk'
Copy-Item -LiteralPath (Join-Path ([Environment]::GetFolderPath('Desktop')) 'Antigravity Usage Supervisor.lnk') -Destination $startMenu -Force
Write-Output "Installed to $installRoot"
if (!$NoLaunch) { Start-Process -FilePath (Join-Path $installRoot 'AntigravityUsageSupervisor.exe') -WindowStyle Hidden }
