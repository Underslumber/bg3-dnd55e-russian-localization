param(
    [string]$RussianPath = "Mods/DnD 5.5e AIO Russian/Localization/Russian/russian.xml",
    [Parameter(Mandatory = $true)]
    [string]$EditsPath
)

$ErrorActionPreference = "Stop"

function Read-XmlDocument {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Path
    )

    $resolvedPath = [System.IO.Path]::GetFullPath($Path)
    if (-not (Test-Path -LiteralPath $resolvedPath)) {
        throw "XML file was not found: '$resolvedPath'."
    }

    [xml]$xml = Get-Content -LiteralPath $resolvedPath -Raw
    if ($null -eq $xml.SelectSingleNode('/contentList')) {
        throw "XML file does not contain '/contentList': '$resolvedPath'."
    }

    return @{
        Path = $resolvedPath
        Xml = $xml
    }
}

function Get-ContentNodeMap {
    param(
        [Parameter(Mandatory = $true)]
        [xml]$Xml
    )

    $map = @{}
    foreach ($node in $Xml.SelectNodes('/contentList/content')) {
        $contentUid = [string]$node.GetAttribute("contentuid")
        if ([string]::IsNullOrWhiteSpace($contentUid)) {
            continue
        }

        if ($map.ContainsKey($contentUid)) {
            throw "Duplicate contentuid found in target XML: '$contentUid'."
        }

        $map[$contentUid] = $node
    }

    return $map
}

function Assert-UniqueEditContentUid {
    param(
        [Parameter(Mandatory = $true)]
        [System.Collections.Generic.HashSet[string]]$Seen,
        [Parameter(Mandatory = $true)]
        [string]$ContentUid,
        [Parameter(Mandatory = $true)]
        [string]$Section
    )

    if (-not $Seen.Add($ContentUid)) {
        throw "Edits file contains duplicate contentuid '$ContentUid' in '$Section'."
    }
}

$russianDocument = Read-XmlDocument -Path $RussianPath
$temporaryRussianPath = "$($russianDocument.Path).tmp"
$validateScriptPath = Join-Path $PSScriptRoot "validate-translation-xml.ps1"

if (-not (Test-Path -LiteralPath $validateScriptPath)) {
    throw "Validation script was not found: '$validateScriptPath'."
}

if (Test-Path -LiteralPath $temporaryRussianPath) {
    Remove-Item -LiteralPath $temporaryRussianPath -Force
}

Copy-Item -LiteralPath $russianDocument.Path -Destination $temporaryRussianPath -Force
$russianDocument = Read-XmlDocument -Path $temporaryRussianPath
$resolvedEditsPath = [System.IO.Path]::GetFullPath($EditsPath)
if (-not (Test-Path -LiteralPath $resolvedEditsPath)) {
    throw "Edits file was not found: '$resolvedEditsPath'."
}

$edits = Get-Content -LiteralPath $resolvedEditsPath -Raw | ConvertFrom-Json -Depth 10
if ($null -eq $edits) {
    throw "Edits file is empty or invalid JSON: '$resolvedEditsPath'."
}

$contentListNode = $russianDocument.Xml.SelectSingleNode('/contentList')
if ($null -eq $contentListNode) {
    throw "Target russian.xml does not contain '/contentList': '$($russianDocument.Path)'."
}

$nodeMap = Get-ContentNodeMap -Xml $russianDocument.Xml
$updatedEntries = New-Object System.Collections.Generic.List[string]
$addedEntries = New-Object System.Collections.Generic.List[string]
$seenEditContentUids = [System.Collections.Generic.HashSet[string]]::new()

$updates = @()
if ($edits.PSObject.Properties.Name -contains "updates" -and $null -ne $edits.updates) {
    $updates = @($edits.updates)
}

foreach ($edit in $updates) {
    $contentUid = [string]$edit.contentuid
    if ([string]::IsNullOrWhiteSpace($contentUid)) {
        throw "Each update entry must contain non-empty 'contentuid'."
    }

    Assert-UniqueEditContentUid -Seen $seenEditContentUids -ContentUid $contentUid -Section "updates"

    if (-not $nodeMap.ContainsKey($contentUid)) {
        throw "Target russian.xml does not contain contentuid '$contentUid' for update."
    }

    $node = $nodeMap[$contentUid]
    if ($edit.PSObject.Properties.Name -contains "version" -and -not [string]::IsNullOrWhiteSpace([string]$edit.version)) {
        $node.SetAttribute("version", [string]$edit.version)
    }

    if ($edit.PSObject.Properties.Name -contains "text") {
        if ([string]::IsNullOrWhiteSpace([string]$edit.text)) {
            throw "Update entry '$contentUid' must contain non-empty 'text' when provided."
        }
        $node.InnerText = [string]$edit.text
    }

    $updatedEntries.Add($contentUid) | Out-Null
}

$adds = @()
if ($edits.PSObject.Properties.Name -contains "adds" -and $null -ne $edits.adds) {
    $adds = @($edits.adds)
}

if (($updates.Count -eq 0) -and ($adds.Count -eq 0)) {
    if (Test-Path -LiteralPath $temporaryRussianPath) {
        Remove-Item -LiteralPath $temporaryRussianPath -Force
    }
    Write-Host "[apply-translation-edits.ps1] No edits requested. Original russian.xml left unchanged."
    return
}

foreach ($edit in $adds) {
    $contentUid = [string]$edit.contentuid
    $version = [string]$edit.version
    $text = [string]$edit.text

    if ([string]::IsNullOrWhiteSpace($contentUid)) {
        throw "Each add entry must contain non-empty 'contentuid'."
    }

    Assert-UniqueEditContentUid -Seen $seenEditContentUids -ContentUid $contentUid -Section "adds"

    if ($nodeMap.ContainsKey($contentUid)) {
        throw "Target russian.xml already contains contentuid '$contentUid'; use 'updates' instead of 'adds'."
    }

    if ([string]::IsNullOrWhiteSpace($version)) {
        throw "Add entry '$contentUid' must contain non-empty 'version'."
    }

    if ([string]::IsNullOrWhiteSpace($text)) {
        throw "Add entry '$contentUid' must contain non-empty 'text'."
    }

    $newNode = $russianDocument.Xml.CreateElement("content")
    $newNode.SetAttribute("contentuid", $contentUid)
    $newNode.SetAttribute("version", $version)
    $newNode.InnerText = $text
    [void]$contentListNode.AppendChild($newNode)
    $nodeMap[$contentUid] = $newNode
    $addedEntries.Add($contentUid) | Out-Null
}

$settings = New-Object System.Xml.XmlWriterSettings
$settings.Encoding = New-Object System.Text.UTF8Encoding($true)
$settings.Indent = $true
$settings.IndentChars = "  "
$settings.NewLineChars = "`n"
$settings.NewLineHandling = [System.Xml.NewLineHandling]::Replace

$writer = [System.Xml.XmlWriter]::Create($russianDocument.Path, $settings)
try {
    $russianDocument.Xml.WriteTo($writer)
} finally {
    $writer.Dispose()
}

try {
    & $validateScriptPath -XmlPath $temporaryRussianPath
    Move-Item -LiteralPath $temporaryRussianPath -Destination $RussianPath -Force
} finally {
    if (Test-Path -LiteralPath $temporaryRussianPath) {
        Remove-Item -LiteralPath $temporaryRussianPath -Force
    }
}

Write-Host "[apply-translation-edits.ps1] Updated entries: $($updatedEntries.Count); Added entries: $($addedEntries.Count)."
if ($updatedEntries.Count -gt 0) {
    Write-Host "[apply-translation-edits.ps1] Updated contentuid: $($updatedEntries -join ', ')"
}
if ($addedEntries.Count -gt 0) {
    Write-Host "[apply-translation-edits.ps1] Added contentuid: $($addedEntries -join ', ')"
}
