param(
    [string]$EnglishPath = ".cache/upstream/english.xml",
    [string]$RussianPath = "Mods/DnD 5.5e AIO Russian/Localization/Russian/russian.xml",
    [string]$OutputDir = "build/translation-diff"
)

$ErrorActionPreference = "Stop"

function Get-LocalizationEntries {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Path
    )

    $resolvedPath = [System.IO.Path]::GetFullPath($Path)
    if (-not (Test-Path -LiteralPath $resolvedPath)) {
        throw "Localization XML was not found: '$resolvedPath'."
    }

    [xml]$xml = Get-Content -LiteralPath $resolvedPath -Raw
    $nodes = $xml.SelectNodes('/contentList/content')
    if ($null -eq $nodes) {
        throw "Localization XML does not contain '/contentList/content' nodes: '$resolvedPath'."
    }

    $entries = @{}
    foreach ($node in $nodes) {
        $contentUid = [string]$node.GetAttribute("contentuid")
        if ([string]::IsNullOrWhiteSpace($contentUid)) {
            continue
        }

        $entries[$contentUid] = [ordered]@{
            contentuid = $contentUid
            version = [string]$node.GetAttribute("version")
            text = [string]$node.InnerText
        }
    }

    return $entries
}

$resolvedOutputDir = [System.IO.Path]::GetFullPath($OutputDir)
New-Item -ItemType Directory -Path $resolvedOutputDir -Force | Out-Null

$englishEntries = Get-LocalizationEntries -Path $EnglishPath
$russianEntries = Get-LocalizationEntries -Path $RussianPath

$englishKeys = [System.Collections.Generic.HashSet[string]]::new([string[]]$englishEntries.Keys)
$russianKeys = [System.Collections.Generic.HashSet[string]]::new([string[]]$russianEntries.Keys)

$missingInRussian = New-Object System.Collections.Generic.List[object]
$versionMismatch = New-Object System.Collections.Generic.List[object]
$staleOnlyInRussian = New-Object System.Collections.Generic.List[object]

foreach ($contentUid in ($englishEntries.Keys | Sort-Object)) {
    $englishEntry = $englishEntries[$contentUid]
    if (-not $russianEntries.ContainsKey($contentUid)) {
        $missingInRussian.Add([pscustomobject]@{
            contentuid = $contentUid
            englishVersion = $englishEntry.version
            englishText = $englishEntry.text
        }) | Out-Null
        continue
    }

    $russianEntry = $russianEntries[$contentUid]
    if ($englishEntry.version -ne $russianEntry.version) {
        $versionMismatch.Add([pscustomobject]@{
            contentuid = $contentUid
            englishVersion = $englishEntry.version
            russianVersion = $russianEntry.version
            englishText = $englishEntry.text
            russianText = $russianEntry.text
        }) | Out-Null
    }
}

foreach ($contentUid in ($russianEntries.Keys | Sort-Object)) {
    if (-not $englishEntries.ContainsKey($contentUid)) {
        $russianEntry = $russianEntries[$contentUid]
        $staleOnlyInRussian.Add([pscustomobject]@{
            contentuid = $contentUid
            russianVersion = $russianEntry.version
            russianText = $russianEntry.text
        }) | Out-Null
    }
}

$summary = [ordered]@{
    generatedAt = (Get-Date).ToString("o")
    englishPath = [System.IO.Path]::GetFullPath($EnglishPath)
    russianPath = [System.IO.Path]::GetFullPath($RussianPath)
    englishCount = $englishEntries.Count
    russianCount = $russianEntries.Count
    missingInRussianCount = $missingInRussian.Count
    versionMismatchCount = $versionMismatch.Count
    staleOnlyInRussianCount = $staleOnlyInRussian.Count
    missingInRussian = $missingInRussian
    versionMismatch = $versionMismatch
    staleOnlyInRussian = $staleOnlyInRussian
}

$summaryJsonPath = Join-Path $resolvedOutputDir "summary.json"
$summaryMdPath = Join-Path $resolvedOutputDir "summary.md"
$candidatesJsonPath = Join-Path $resolvedOutputDir "candidates.json"

$summary | ConvertTo-Json -Depth 6 | Set-Content -LiteralPath $summaryJsonPath -Encoding utf8

$candidates = [ordered]@{
    generatedAt = (Get-Date).ToString("o")
    source = [ordered]@{
        englishPath = [System.IO.Path]::GetFullPath($EnglishPath)
        russianPath = [System.IO.Path]::GetFullPath($RussianPath)
    }
    updates = @(
        $versionMismatch | ForEach-Object {
            [ordered]@{
                contentuid = $_.contentuid
                version = $_.englishVersion
                text = $_.russianText
                englishText = $_.englishText
                russianVersion = $_.russianVersion
            }
        }
    )
    adds = @(
        $missingInRussian | ForEach-Object {
            [ordered]@{
                contentuid = $_.contentuid
                version = $_.englishVersion
                text = ""
                englishText = $_.englishText
            }
        }
    )
}

$candidates | ConvertTo-Json -Depth 6 | Set-Content -LiteralPath $candidatesJsonPath -Encoding utf8

$isUpToDate = ($missingInRussian.Count -eq 0) -and ($versionMismatch.Count -eq 0) -and ($staleOnlyInRussian.Count -eq 0)

$mdLines = @(
    "# Translation diff summary",
    "",
    "- Generated: $($summary.generatedAt)",
    "- English entries: $($summary.englishCount)",
    "- Russian entries: $($summary.russianCount)",
    "- Missing in Russian: $($summary.missingInRussianCount)",
    "- Version mismatches: $($summary.versionMismatchCount)",
    "- Stale only in Russian: $($summary.staleOnlyInRussianCount)",
    ""
)

if ($isUpToDate) {
    $mdLines += "Перевод уже актуален, дополнительные действия не требуются."
} else {
    $mdLines += ""
    $mdLines += "## Local workflow"
    $mdLines += "1. Update upstream cache: ``scripts/get-upstream-english.ps1``"
    $mdLines += "2. Refresh diff: ``scripts/compare-translation.ps1``"
    $mdLines += "3. Edit ``build/translation-diff/candidates.json``"
    $mdLines += "4. Apply changes: ``scripts/apply-translation-edits.ps1 -EditsPath build/translation-diff/candidates.json``"
}

$mdLines += ""
$mdLines += "## Missing in Russian"
if ($missingInRussian.Count -eq 0) {
    $mdLines += "- none"
} else {
    $mdLines += ($missingInRussian | Select-Object -First 50 | ForEach-Object {
        "- ``$($_.contentuid)`` v$($_.englishVersion): $($_.englishText)"
    })
}

$mdLines += ""
$mdLines += "## Version mismatches"
if ($versionMismatch.Count -eq 0) {
    $mdLines += "- none"
} else {
    $mdLines += ($versionMismatch | Select-Object -First 50 | ForEach-Object {
        "- ``$($_.contentuid)`` en=v$($_.englishVersion), ru=v$($_.russianVersion)"
    })
}

$mdLines += ""
$mdLines += "## Stale only in Russian"
if ($staleOnlyInRussian.Count -eq 0) {
    $mdLines += "- none"
} else {
    $mdLines += ($staleOnlyInRussian | Select-Object -First 50 | ForEach-Object {
        "- ``$($_.contentuid)`` v$($_.russianVersion): $($_.russianText)"
    })
}

Set-Content -LiteralPath $summaryMdPath -Value $mdLines -Encoding utf8

Write-Host "[compare-translation.ps1] Summary written to '$summaryJsonPath' and '$summaryMdPath'."
Write-Host "[compare-translation.ps1] Editable candidate file written to '$candidatesJsonPath'."
Write-Host "[compare-translation.ps1] Missing=$($missingInRussian.Count); VersionMismatch=$($versionMismatch.Count); StaleOnlyInRussian=$($staleOnlyInRussian.Count)."
if ($isUpToDate) {
    Write-Host "[compare-translation.ps1] Перевод уже актуален, дополнительные действия не требуются."
}
