param(
    [string]$RussianPath = "Mods/DnD 5.5e AIO Russian/Localization/Russian/russian.xml",
    [string]$EnglishPath = ".cache/upstream/english.xml",
    [string]$OutputDir = "build/translation-diff",
    [string]$EditsPath = ""
)

$ErrorActionPreference = "Stop"

$getUpstreamScriptPath = Join-Path $PSScriptRoot "get-upstream-english.ps1"
$compareScriptPath = Join-Path $PSScriptRoot "compare-translation.ps1"
$applyScriptPath = Join-Path $PSScriptRoot "apply-translation-edits.ps1"

foreach ($scriptPath in @($getUpstreamScriptPath, $compareScriptPath, $applyScriptPath)) {
    if (-not (Test-Path -LiteralPath $scriptPath)) {
        throw "Required script was not found: '$scriptPath'."
    }
}

$resolvedOutputDir = [System.IO.Path]::GetFullPath($OutputDir)
$resolvedProvidedEditsPath = ""
if (-not [string]::IsNullOrWhiteSpace($EditsPath)) {
    $resolvedProvidedEditsPath = [System.IO.Path]::GetFullPath($EditsPath)
}
$workingDiffDir = Join-Path $env:TEMP ("bg3-translation-update-" + [guid]::NewGuid().ToString("N"))
New-Item -ItemType Directory -Path $workingDiffDir -Force | Out-Null

try {
    & $getUpstreamScriptPath -OutputPath $EnglishPath -Force
    & $compareScriptPath -EnglishPath $EnglishPath -RussianPath $RussianPath -OutputDir $workingDiffDir

    New-Item -ItemType Directory -Path $resolvedOutputDir -Force | Out-Null
    Get-ChildItem -LiteralPath $workingDiffDir | ForEach-Object {
        $destinationPath = Join-Path $resolvedOutputDir $_.Name
        if ($resolvedProvidedEditsPath -and ([System.IO.Path]::GetFullPath($destinationPath) -eq $resolvedProvidedEditsPath) -and (Test-Path -LiteralPath $resolvedProvidedEditsPath)) {
            return
        }
        Copy-Item -LiteralPath $_.FullName -Destination $resolvedOutputDir -Recurse -Force
    }

    $summaryJsonPath = Join-Path $workingDiffDir "summary.json"
    if (-not (Test-Path -LiteralPath $summaryJsonPath)) {
        throw "Translation summary was not found: '$summaryJsonPath'."
    }

    $summary = Get-Content -LiteralPath $summaryJsonPath -Raw | ConvertFrom-Json -Depth 10
    $hasDiff = ($summary.missingInRussianCount -gt 0) -or ($summary.versionMismatchCount -gt 0) -or ($summary.staleOnlyInRussianCount -gt 0)

    if (-not $hasDiff) {
        Write-Host "[update-translation.ps1] Перевод уже актуален, дополнительные действия не требуются."
        return
    }

    if ([string]::IsNullOrWhiteSpace($EditsPath)) {
        Write-Host "[update-translation.ps1] Найдены изменения перевода. Подготовьте правки в '$([System.IO.Path]::GetFullPath((Join-Path $resolvedOutputDir "candidates.json")))' и затем запустите повторно с '-EditsPath'."
        return
    }

    $effectiveEditsPath = [System.IO.Path]::GetFullPath($EditsPath)
    if (-not (Test-Path -LiteralPath $effectiveEditsPath)) {
        throw "Prepared edits file was not found: '$effectiveEditsPath'."
    }

    & $applyScriptPath -RussianPath $RussianPath -EditsPath $effectiveEditsPath

    Write-Host "[update-translation.ps1] Обновление перевода завершено. Результат записан в '$([System.IO.Path]::GetFullPath($RussianPath))'."
} finally {
    if (Test-Path -LiteralPath $workingDiffDir) {
        Remove-Item -LiteralPath $workingDiffDir -Recurse -Force
    }
}
