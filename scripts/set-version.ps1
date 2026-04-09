param(
    [Parameter(Mandatory = $true)]
    [string]$VersionTag,
    [string]$MetaPath = "Mods/DnD 5.5e AIO Russian/meta.lsx"
)

$ErrorActionPreference = "Stop"

function Convert-VersionTagToVersion64 {
    param(
        [string]$Tag
    )

    $normalized = $Tag
    if ($normalized.StartsWith("v")) {
        $normalized = $normalized.Substring(1)
    }

    if ($normalized -notmatch '^\d+(\.\d+){0,3}$') {
        throw "Version tag '$Tag' is invalid. Expected format: vX.Y.Z or X.Y.Z"
    }

    $parts = $normalized.Split(".")
    $numbers = @(0, 0, 0, 0)
    for ($i = 0; $i -lt $parts.Length; $i++) {
        $numbers[$i] = [int]$parts[$i]
    }

    return ([int64]$numbers[0] -shl 55) -bor ([int64]$numbers[1] -shl 47) -bor ([int64]$numbers[2] -shl 31) -bor [int64]$numbers[3]
}

$resolvedMetaPath = [System.IO.Path]::GetFullPath($MetaPath)
if (-not (Test-Path -LiteralPath $resolvedMetaPath)) {
    throw "meta.lsx was not found: '$resolvedMetaPath'."
}

$resolvedVersion64 = Convert-VersionTagToVersion64 -Tag $VersionTag
$metaContent = Get-Content -LiteralPath $resolvedMetaPath -Raw

$versionPattern = '(<attribute id="Version64" type="int64" value=")\d+("/>)'
if ($metaContent -notmatch $versionPattern) {
    throw "Version64 attributes were not found in '$resolvedMetaPath'."
}
$updatedMeta = $metaContent -replace $versionPattern, "`${1}$resolvedVersion64`${2}"

$utf8Bom = New-Object System.Text.UTF8Encoding($true)
[System.IO.File]::WriteAllText($resolvedMetaPath, $updatedMeta, $utf8Bom)

Write-Host "[set-version.ps1] Updated '$resolvedMetaPath' to Version64=$resolvedVersion64 (from tag '$VersionTag')."
