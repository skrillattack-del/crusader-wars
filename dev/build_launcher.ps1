$ErrorActionPreference = 'Stop'
$probeRoot = Join-Path $PSScriptRoot 'spikes/g1_3k_io'
$appRoot = Join-Path $PSScriptRoot 'app'
# OneDrive can briefly lock build outputs; clear them with retries before PyInstaller.
foreach ($stale in @((Join-Path $PSScriptRoot 'build\CW2-Launcher'),
                    (Join-Path $PSScriptRoot 'dist\CW2-Launcher.exe'))) {
  if (Test-Path $stale) {
    $cleared = $false
    foreach ($attempt in 1..3) {
      try { Remove-Item -Recurse -Force -LiteralPath $stale -ErrorAction Stop; $cleared = $true; break }
      catch { Start-Sleep -Seconds (5 * $attempt) }
    }
    if (-not $cleared -and (Test-Path $stale)) {
      throw "Could not clear stale build output (locked by OneDrive or a running launcher): $stale"
    }
  }
}
$buildArgs = @(
  '--noconfirm', '--clean', '--onefile', '--windowed', '--name', 'CW2-Launcher',
  '--distpath', (Join-Path $PSScriptRoot 'dist'),
  '--workpath', (Join-Path $PSScriptRoot 'build'),
  '--specpath', $PSScriptRoot,
  '--paths', $probeRoot,
  '--add-data', "$(Join-Path $appRoot 'ui\index.html');ui",
  '--add-data', "$(Join-Path $probeRoot 'probe.lua');.",
  (Join-Path $appRoot 'main.py')
)
python -m PyInstaller @buildArgs
if ($LASTEXITCODE -ne 0) { throw 'Executable build failed.' }
Write-Output "Built $(Join-Path $PSScriptRoot 'dist\CW2-Launcher.exe')"
