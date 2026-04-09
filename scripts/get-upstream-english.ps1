param(
    [string]$UpstreamEnglishUrl = "https://raw.githubusercontent.com/Yoonmoonsik/dnd55e/main/Mods/DnD2024_897914ef-5c96-053c-44af-0be823f895fe/Localization/English/english.xml",
    [string]$OutputPath = ".cache/upstream/english.xml",
    [switch]$Force
)

$ErrorActionPreference = "Stop"

if ([string]::IsNullOrWhiteSpace($UpstreamEnglishUrl)) {
    throw "UpstreamEnglishUrl must not be empty."
}

$resolvedOutputPath = [System.IO.Path]::GetFullPath($OutputPath)
$outputDirectory = Split-Path -Parent $resolvedOutputPath
if (-not (Test-Path -LiteralPath $outputDirectory)) {
    New-Item -ItemType Directory -Path $outputDirectory -Force | Out-Null
}

$requestParameters = @{
    Uri = $UpstreamEnglishUrl
    OutFile = $resolvedOutputPath
    UseBasicParsing = $true
    TimeoutSec = 120
}

if ($Force) {
    $requestParameters["Headers"] = @{
        "Cache-Control" = "no-cache"
    }
}

Invoke-WebRequest @requestParameters

[xml]$englishXml = Get-Content -LiteralPath $resolvedOutputPath -Raw
$rootNode = $englishXml.SelectSingleNode('/contentList')
if ($null -eq $rootNode) {
    throw "Downloaded file is not a valid BG3 localization XML: '$resolvedOutputPath'."
}

$contentCount = $englishXml.SelectNodes('/contentList/content').Count
$fileInfo = Get-Item -LiteralPath $resolvedOutputPath

Write-Host "[get-upstream-english.ps1] Saved upstream english.xml to '$resolvedOutputPath'."
Write-Host "[get-upstream-english.ps1] Entries: $contentCount; Size: $($fileInfo.Length) bytes; Updated: $($fileInfo.LastWriteTime.ToString("o"))."
