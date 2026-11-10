$ErrorActionPreference='Stop'
$taskRoot=Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath $taskRoot
$env:PYTHONIOENCODING='utf-8'
$taskPython=Join-Path $taskRoot '.venv/Scripts/python.exe'
if(!(Test-Path -LiteralPath $taskPython) -or !(Test-Path -LiteralPath 'frontend/dist/index.html')){& "$PSScriptRoot/setup.ps1"}
if(!(Test-Path -LiteralPath '.env')){Copy-Item -LiteralPath '.env.example' -Destination '.env'}
try{$taskHealth=Invoke-RestMethod -Uri 'http://127.0.0.1:8765/api/health' -TimeoutSec 2}catch{$taskHealth=$null}
if($taskHealth -and $taskHealth.service -eq 'greenhouse-platform'){Write-Host '系统已经运行：http://127.0.0.1:8765';exit 0}
Write-Host '正在启动本机系统。保持此窗口运行；按Ctrl+C停止。'
Write-Host '打开浏览器访问：http://127.0.0.1:8765'
& $taskPython -m uvicorn backend.app:app --host 127.0.0.1 --port 8765
