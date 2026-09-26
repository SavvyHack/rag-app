$ErrorActionPreference = 'Stop'
$taskRoot = $PSScriptRoot
$taskPython = Join-Path $taskRoot 'venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $taskPython)) {
    throw 'Create venv and install requirements.txt before building.'
}
Push-Location $taskRoot
try {
    & $taskPython -m unittest discover -s tests -v
    if ($LASTEXITCODE -ne 0) { throw 'Regression tests failed.' }
    $taskExe = Join-Path $taskRoot 'dist\OfflineRAG.exe'
    $taskBackup = Join-Path $taskRoot 'dist\OfflineRAG.previous.exe'
    if ((Test-Path -LiteralPath $taskExe) -and -not (Test-Path -LiteralPath $taskBackup)) {
        Copy-Item -LiteralPath $taskExe -Destination $taskBackup
    }
    & $taskPython -m PyInstaller --noconfirm OfflineRAG.spec
    if ($LASTEXITCODE -ne 0) { throw 'Executable build failed.' }
    Write-Host "Built $taskExe"
} finally {
    Pop-Location
}
