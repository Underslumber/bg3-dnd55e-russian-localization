param(
    [Parameter(Mandatory = $true)]
    [string]$XmlPath
)

$ErrorActionPreference = "Stop"

$resolvedXmlPath = [System.IO.Path]::GetFullPath($XmlPath)
if (-not (Test-Path -LiteralPath $resolvedXmlPath)) {
    throw "XML file was not found: '$resolvedXmlPath'."
}

[xml]$xml = Get-Content -LiteralPath $resolvedXmlPath -Raw
$contentListNode = $xml.SelectSingleNode('/contentList')
if ($null -eq $contentListNode) {
    throw "XML validation failed: missing '/contentList' in '$resolvedXmlPath'."
}

$contentNodes = $xml.SelectNodes('/contentList/content')
if ($null -eq $contentNodes -or $contentNodes.Count -lt 1) {
    throw "XML validation failed: no '/contentList/content' entries found in '$resolvedXmlPath'."
}

$seen = [System.Collections.Generic.HashSet[string]]::new()
foreach ($node in $contentNodes) {
    $contentUid = [string]$node.GetAttribute("contentuid")
    if ([string]::IsNullOrWhiteSpace($contentUid)) {
        throw "XML validation failed: found content node without 'contentuid' in '$resolvedXmlPath'."
    }

    if (-not $seen.Add($contentUid)) {
        throw "XML validation failed: duplicate contentuid '$contentUid' in '$resolvedXmlPath'."
    }

    $version = [string]$node.GetAttribute("version")
    if ([string]::IsNullOrWhiteSpace($version)) {
        throw "XML validation failed: contentuid '$contentUid' has empty 'version' in '$resolvedXmlPath'."
    }
}

Write-Host "[validate-translation-xml.ps1] XML is valid: '$resolvedXmlPath'. Entries=$($contentNodes.Count)."
