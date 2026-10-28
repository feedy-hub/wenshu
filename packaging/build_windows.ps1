$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
$buildPython = Join-Path $projectRoot '.build-venv\Scripts\python.exe'
python -m venv (Join-Path $projectRoot '.build-venv')
if ($LASTEXITCODE -ne 0) { throw 'Failed to create the build environment.' }
& $buildPython -m pip install -r (Join-Path $projectRoot 'requirements.txt') pyinstaller
if ($LASTEXITCODE -ne 0) { throw 'Failed to install build dependencies.' }
& $buildPython -m PyInstaller --noconfirm --clean --onefile --windowed --name '文枢' --icon (Join-Path $PSScriptRoot 'Wenshu.ico') --add-data "$projectRoot\static;static" --add-data "$projectRoot\samples;samples" --distpath (Join-Path $projectRoot 'dist') --workpath (Join-Path $projectRoot 'build') --specpath (Join-Path $projectRoot 'build') (Join-Path $projectRoot 'launch.py')
if ($LASTEXITCODE -ne 0) { throw 'Windows packaging failed.' }
