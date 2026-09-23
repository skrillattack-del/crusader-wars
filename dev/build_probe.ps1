$ErrorActionPreference = 'Stop'
$probeRoot = Join-Path $PSScriptRoot 'spikes/g1_3k_io'
python -m PyInstaller --noconfirm --clean --onefile --windowed --name CW2-G1-Probe --distpath (Join-Path $PSScriptRoot 'dist') --workpath (Join-Path $PSScriptRoot 'build') --specpath $PSScriptRoot --add-data "$(Join-Path $probeRoot 'probe.lua');." (Join-Path $probeRoot 'probe_app.py')
if ($LASTEXITCODE -ne 0) { throw 'Executable build failed.' }
