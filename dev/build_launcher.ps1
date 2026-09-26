$ErrorActionPreference = 'Stop'
$probeRoot = Join-Path $PSScriptRoot 'spikes/g1_3k_io'
$appRoot   = Join-Path $PSScriptRoot 'app'

# Wipe the entire work directory and .spec so PyInstaller always re-collects
# data files (index.html, probe.lua, etc.). --clean only resets the analysis
# cache; without this, changes to --add-data sources are silently ignored.
foreach ($stale in @(
    (Join-Path $PSScriptRoot 'build'),
    (Join-Path $PSScriptRoot 'CW2-Launcher.spec')
  )) {
  if (Test-Path $stale) { Remove-Item -Recurse -Force -LiteralPath $stale }
}

# OneDrive can briefly lock the old exe; clear it with retries.
$oldExe = Join-Path $PSScriptRoot 'dist\CW2-Launcher.exe'
if (Test-Path $oldExe) {
  $cleared = $false
  foreach ($attempt in 1..3) {
    try { Remove-Item -Force -LiteralPath $oldExe -ErrorAction Stop; $cleared = $true; break }
    catch { Start-Sleep -Seconds (5 * $attempt) }
  }
  if (-not $cleared -and (Test-Path $oldExe)) {
    throw "Could not clear stale exe (locked by OneDrive or a running launcher): $oldExe"
  }
}
$buildArgs = @(
  '--noconfirm', '--clean', '--onefile', '--windowed', '--name', 'CW2-Launcher',
  '--distpath', (Join-Path $PSScriptRoot 'dist'),
  '--workpath', (Join-Path $PSScriptRoot 'build'),
  '--specpath', $PSScriptRoot,
  '--paths', $probeRoot,
  '--paths', (Join-Path $PSScriptRoot 'spikes/g2_ck3_writeback/patcher'),
  '--paths', (Join-Path $PSScriptRoot 'battle_math'),
  '--add-data', "$(Join-Path $appRoot 'ui\index.html');ui",
  '--add-data', "$(Join-Path $appRoot 'ui\skins');ui\skins",
  '--add-data', "$(Join-Path $probeRoot 'probe.lua');.",
  '--add-data', "$(Join-Path $probeRoot 'frontend_open.lua');.",
  (Join-Path $appRoot 'main.py')
)
python -m PyInstaller @buildArgs
if ($LASTEXITCODE -ne 0) { throw 'Executable build failed.' }
Write-Output "Built $(Join-Path $PSScriptRoot 'dist\CW2-Launcher.exe')"
