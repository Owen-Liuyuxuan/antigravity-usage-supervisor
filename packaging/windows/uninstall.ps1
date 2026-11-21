$ErrorActionPreference = 'Stop'
if (Get-Process AntigravityUsageSupervisor -ErrorAction SilentlyContinue) { throw 'Please exit Antigravity Usage Supervisor first.' }
$expected = [IO.Path]::GetFullPath((Join-Path $env:LOCALAPPDATA 'Programs/AntigravityUsageSupervisor'))
if (Test-Path -LiteralPath $expected) {
    $resolved = (Resolve-Path -LiteralPath $expected).Path
    if ($resolved -ne $expected -or (Get-Item -LiteralPath $resolved).Attributes.HasFlag([IO.FileAttributes]::ReparsePoint)) { throw 'Unexpected installation path' }
    Remove-Item -LiteralPath $resolved -Recurse -Force
}
Remove-ItemProperty -LiteralPath 'HKCU:\Software\Microsoft\Windows\CurrentVersion\Run' -Name AntigravityUsageSupervisor -ErrorAction SilentlyContinue
foreach ($link in @((Join-Path ([Environment]::GetFolderPath('Desktop')) 'Antigravity Usage Supervisor.lnk'), (Join-Path ([Environment]::GetFolderPath('StartMenu')) 'Programs/Antigravity Usage Supervisor.lnk'))) {
    if (Test-Path -LiteralPath $link) { Remove-Item -LiteralPath $link }
}
Write-Output 'Uninstalled. Personal settings and Python/.NET installations are preserved.'
