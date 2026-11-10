$ErrorActionPreference='Stop'
$taskRoot=Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath $taskRoot
$env:PYTHONIOENCODING='utf-8'
if(!(Test-Path -LiteralPath '.venv/Scripts/python.exe')){
  $taskPython=if(Test-Path -LiteralPath 'D:/python/python.exe'){'D:/python/python.exe'}else{(Get-Command python -ErrorAction Stop).Source}
  & $taskPython -m venv --system-site-packages .venv
  if($LASTEXITCODE -ne 0){throw '创建Python虚拟环境失败'}
}
& '.venv/Scripts/python.exe' -m pip install -r requirements.txt
if($LASTEXITCODE -ne 0){throw '依赖安装失败，请检查网络或Python包镜像设置'}
if(!(Test-Path -LiteralPath '.env')){Copy-Item -LiteralPath '.env.example' -Destination '.env'}
Push-Location frontend
try{& npm.cmd ci --no-audit --no-fund;if($LASTEXITCODE -ne 0){throw '前端依赖安装失败'};& npm.cmd run build;if($LASTEXITCODE -ne 0){throw '前端构建失败'}}finally{Pop-Location}
Write-Host '安装完成。运行启动系统.cmd，然后在数据设置中导入真实记录并训练模型。'
