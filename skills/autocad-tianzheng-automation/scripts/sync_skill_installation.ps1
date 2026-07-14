[CmdletBinding()]
param(
    [string]$Source = (Split-Path -Parent $PSScriptRoot),
    [string]$Destination = "$HOME\.agents\skills\autocad-tianzheng-automation",
    [switch]$Apply,
    [switch]$VerifyHash
)

$ErrorActionPreference = 'Stop'
$sourceRoot = (Resolve-Path -LiteralPath $Source).Path
$excludedNames = @('artifacts', '.pytest_cache', '__pycache__')
$files = Get-ChildItem -LiteralPath $sourceRoot -Recurse -File | Where-Object {
    $relativeParts = $_.FullName.Substring($sourceRoot.Length).TrimStart('\').Split('\')
    -not ($relativeParts | Where-Object { $_ -in $excludedNames }) -and $_.Extension -ne '.pyc'
}

$changes = foreach ($file in $files) {
    $relative = $file.FullName.Substring($sourceRoot.Length).TrimStart('\')
    $target = Join-Path $Destination $relative
    $sourceHash = (Get-FileHash -LiteralPath $file.FullName -Algorithm SHA256).Hash
    $targetHash = if (Test-Path -LiteralPath $target) { (Get-FileHash -LiteralPath $target -Algorithm SHA256).Hash } else { $null }
    [pscustomobject]@{ RelativePath=$relative; Action=if ($targetHash -eq $sourceHash) {'UNCHANGED'} elseif ($targetHash) {'UPDATE'} else {'ADD'}; SourceSHA256=$sourceHash; DestinationSHA256=$targetHash }
}

[pscustomobject]@{ Mode=if($Apply){'APPLY'}else{'DRY_RUN'}; Source=$sourceRoot; Destination=$Destination; DeletesUnknownFiles=$false; Changes=$changes } | ConvertTo-Json -Depth 5
if (-not $Apply) { return }

foreach ($change in $changes | Where-Object Action -ne 'UNCHANGED') {
    $sourceFile = Join-Path $sourceRoot $change.RelativePath
    $targetFile = Join-Path $Destination $change.RelativePath
    New-Item -ItemType Directory -Force -Path (Split-Path -Parent $targetFile) | Out-Null
    Copy-Item -LiteralPath $sourceFile -Destination $targetFile -Force
    if ($VerifyHash) {
        $actual = (Get-FileHash -LiteralPath $targetFile -Algorithm SHA256).Hash
        if ($actual -ne $change.SourceSHA256) { throw "哈希校验失败: $($change.RelativePath)" }
    }
}
