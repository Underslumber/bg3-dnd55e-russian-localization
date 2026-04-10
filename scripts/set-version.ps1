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
$utf8Encoding = [System.Text.UTF8Encoding]::new($false)
$metaContent = [System.IO.File]::ReadAllText($resolvedMetaPath, $utf8Encoding)
[xml]$metaXml = $metaContent

# Explicitly target ModuleInfo/Version64 via XML path to avoid touching Dependencies/PublishVersion.
$moduleInfoVersionNode = $metaXml.SelectSingleNode('/save/region/node/children/node[@id="ModuleInfo"]/attribute[@id="Version64" and @type="int64"]')
if ($null -eq $moduleInfoVersionNode) {
    throw "ModuleInfo/Version64 attribute was not found in '$resolvedMetaPath'."
}

# Replace only the Version64 attribute that appears inside ModuleInfo before its <children> block.
$moduleInfoVersionPattern = '(?s)(<node id="ModuleInfo">\s*(?:(?!<children>).)*?<attribute id="Version64" type="int64" value=")\d+("/>)'
if ($metaContent -notmatch $moduleInfoVersionPattern) {
    throw "ModuleInfo/Version64 attribute was not found in '$resolvedMetaPath'."
}

$updatedMeta = [regex]::Replace(
    $metaContent,
    $moduleInfoVersionPattern,
    "`${1}$resolvedVersion64`${2}",
    1
)

[System.IO.File]::WriteAllText($resolvedMetaPath, $updatedMeta, $utf8Encoding)

Write-Host "[set-version.ps1] Updated '$resolvedMetaPath' to Version64=$resolvedVersion64 (from tag '$VersionTag')."
