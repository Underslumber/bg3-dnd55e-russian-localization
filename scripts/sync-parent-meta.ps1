param(
    [Parameter(Mandatory = $true)]
    [string]$ParentMetaPath,
    [string]$TargetMetaPath = "Mods/DnD 5.5e AIO Russian/meta.lsx"
)

$ErrorActionPreference = "Stop"

$resolvedParentMetaPath = [System.IO.Path]::GetFullPath($ParentMetaPath)
$resolvedTargetMetaPath = [System.IO.Path]::GetFullPath($TargetMetaPath)

if (-not (Test-Path -LiteralPath $resolvedParentMetaPath)) {
    throw "Parent meta.lsx was not found: '$resolvedParentMetaPath'."
}

if (-not (Test-Path -LiteralPath $resolvedTargetMetaPath)) {
    throw "Target meta.lsx was not found: '$resolvedTargetMetaPath'."
}

$parentRaw = Get-Content -LiteralPath $resolvedParentMetaPath -Raw
$targetRaw = Get-Content -LiteralPath $resolvedTargetMetaPath -Raw

[xml]$parentXml = $parentRaw
[xml]$targetXml = $targetRaw

$parentModuleInfo = $parentXml.SelectSingleNode('/save/region/node/children/node[@id="ModuleInfo"]')
if ($null -eq $parentModuleInfo) {
    throw "ModuleInfo node was not found in parent meta: '$resolvedParentMetaPath'."
}

$requiredFields = @("Folder", "MD5", "Name", "PublishHandle", "UUID", "Version64")
$sourceValues = @{}

foreach ($field in $requiredFields) {
    $node = $parentModuleInfo.SelectSingleNode("attribute[@id='$field']")
    if ($null -eq $node) {
        throw "Required parent ModuleInfo attribute '$field' is missing in '$resolvedParentMetaPath'."
    }

    $value = $node.GetAttribute("value")
    if ([string]::IsNullOrWhiteSpace($value)) {
        throw "Required parent ModuleInfo attribute '$field' has empty value in '$resolvedParentMetaPath'."
    }

    $sourceValues[$field] = $value
}

$targetDependencyNode = $targetXml.SelectSingleNode('/save/region/node/children/node[@id="Dependencies"]/children/node[@id="ModuleShortDesc"]')
if ($null -eq $targetDependencyNode) {
    throw "Dependencies/ModuleShortDesc node was not found in target meta: '$resolvedTargetMetaPath'."
}

$changedFields = @()
foreach ($field in $requiredFields) {
    $targetAttr = $targetDependencyNode.SelectSingleNode("attribute[@id='$field']")
    if ($null -eq $targetAttr) {
        throw "Target Dependencies/ModuleShortDesc attribute '$field' is missing in '$resolvedTargetMetaPath'."
    }

    $currentValue = $targetAttr.GetAttribute("value")
    $newValue = [string]$sourceValues[$field]
    if ($currentValue -ne $newValue) {
        $targetAttr.SetAttribute("value", $newValue)
        $changedFields += $field
    }
}

if ($changedFields.Count -eq 0) {
    Write-Host "[sync-parent-meta.ps1] No changes needed. Target dependency data is already up to date."
} else {
    $utf8Bom = New-Object System.Text.UTF8Encoding($true)
    $settings = New-Object System.Xml.XmlWriterSettings
    $settings.Encoding = $utf8Bom
    $settings.Indent = $true
    $settings.IndentChars = "    "
    $settings.NewLineChars = "`n"
    $settings.NewLineHandling = [System.Xml.NewLineHandling]::Replace

    $writer = [System.Xml.XmlWriter]::Create($resolvedTargetMetaPath, $settings)
    try {
        $targetXml.WriteTo($writer)
    } finally {
        $writer.Dispose()
    }

    Write-Host ("[sync-parent-meta.ps1] Updated fields: " + ($changedFields -join ", "))
}
