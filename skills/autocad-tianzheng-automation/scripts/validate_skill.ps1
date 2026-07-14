[CmdletBinding()]
param()

$ErrorActionPreference = 'Stop'
$env:PYTHONUTF8 = '1'
$skillRoot = Split-Path -Parent $PSScriptRoot
$validator = Join-Path $HOME '.codex\skills\.system\skill-creator\scripts\quick_validate.py'
if (-not (Test-Path -LiteralPath $validator -PathType Leaf)) {
    throw "未找到 skill-creator 校验器: $validator"
}
python $validator $skillRoot
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
