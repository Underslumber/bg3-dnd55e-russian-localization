param(
    [string]$DivinePath = "Divine",
    [string]$Workspace = (Get-Location).Path,
    [string]$VersionTag = "",
    [string]$ModFolder = "DnD 5.5e AIO Russian",
    [string]$PackageName = "DnD 5.5e AIO Russian.pak",
    [string]$ArchiveBaseName = "DnD 5.5e AIO Russian",
    [string]$ModName = "DnD 5.5e All-in-One BEYOND Russian Localization",
    [string]$ModUuid = "6401e84d-daf2-416d-adeb-99c03a2487a6",
    [string]$ModAuthor = "Underslumber Team",
    [string]$ModDescription = "Русская локализация мода, который добавляет и обновляет контент в соответствии с правилами DnD 5.5e и другими источниками, включая предыстории, классы, таланты, расы, заклинания и многое другое. Это отдельный мод локализации и он требует установленный оригинальный мод.",
    [string]$ModGroup = "6401e84d-daf2-416d-adeb-99c03a2487a6",
    [string]$DependencyUuid = "897914ef-5c96-053c-44af-0be823f895fe",
    [string]$DependencyVersion64 = "36028797018963968"
)

$ErrorActionPreference = "Stop"

function Convert-VersionTagToVersion64 {
    param(
        [string]$Tag,
        [string]$RepoPath
    )

    $normalized = $Tag
    if ($normalized.StartsWith("v")) {
        $normalized = $normalized.Substring(1)
    }

    if ($normalized -notmatch '^(?<base>\d+\.\d+\.\d+)(?:-(?<suffix>[0-9A-Za-z][0-9A-Za-z.-]*))?$') {
        throw "Version tag '$Tag' is invalid. Expected format: vX.Y.Z or vX.Y.Z-suffix"
    }

    $baseVersion = $Matches.base
    $suffix = $Matches.suffix
    $parts = $baseVersion.Split(".")
    $numbers = @(0, 0, 0, 0)
    for ($i = 0; $i -lt $parts.Length; $i++) {
        $numbers[$i] = [int]$parts[$i]
    }

    if ($suffix) {
        $resolvedRepoPath = [System.IO.Path]::GetFullPath($RepoPath)
        $matchingTags = @()

        try {
            $matchingTags = @(git -C $resolvedRepoPath tag --list "v$baseVersion-*" 2>$null | Where-Object { $_ -and $_ -ne $Tag })
        } catch {
            $matchingTags = @()
        }

        $numbers[3] = $matchingTags.Count + 1
    }

    return ([int64]$numbers[0] -shl 55) -bor ([int64]$numbers[1] -shl 47) -bor ([int64]$numbers[2] -shl 31) -bor [int64]$numbers[3]
}

function Get-ModuleInfoVersion64 {
    param(
        [string]$MetaPath
    )

    $utf8Encoding = [System.Text.UTF8Encoding]::new($false)
    $metaContent = [System.IO.File]::ReadAllText($MetaPath, $utf8Encoding)
    $moduleInfoPattern = '(?s)(<node id="ModuleInfo">\s*(?:(?!<children>).)*?<attribute id="Version64" type="int64" value=")(\d+)("/>)'
    $match = [System.Text.RegularExpressions.Regex]::Match($metaContent, $moduleInfoPattern)
    if (-not $match.Success) {
        throw "ModuleInfo/Version64 attribute was not found in '$MetaPath'."
    }

    return [int64]$match.Groups[2].Value
}

function Set-ModuleInfoVersion64 {
    param(
        [string]$MetaPath,
        [int64]$Version64
    )

    $utf8Encoding = [System.Text.UTF8Encoding]::new($false)
    $metaContent = [System.IO.File]::ReadAllText($MetaPath, $utf8Encoding)
    $moduleInfoPattern = '(?s)(<node id="ModuleInfo">\s*(?:(?!<children>).)*?<attribute id="Version64" type="int64" value=")\d+("/>)'
    $updatedMetaContent = [System.Text.RegularExpressions.Regex]::Replace(
        $metaContent,
        $moduleInfoPattern,
        "`${1}$Version64`${2}",
        1
    )

    if ($updatedMetaContent -ceq $metaContent) {
        throw "ModuleInfo/Version64 attribute was not found in '$MetaPath'."
    }

    [System.IO.File]::WriteAllText($MetaPath, $updatedMetaContent, $utf8Encoding)
}

$workspacePath = [System.IO.Path]::GetFullPath($Workspace)
$modsPath = Join-Path $workspacePath "Mods"
$modPath = Join-Path $modsPath $ModFolder
$metaPath = Join-Path $modPath "meta.lsx"
$buildPath = Join-Path $workspacePath "build"
$stagingRoot = Join-Path $env:TEMP "bg3-dnd55e-russian-localization-stage"
$stagingPath = Join-Path $stagingRoot "build-stage"
$packagePath = Join-Path $buildPath $PackageName
$tempPackagePath = Join-Path $env:TEMP $PackageName
$archiveName = $ArchiveBaseName
if ($VersionTag) {
    $archiveName = "$ArchiveBaseName $VersionTag"
}
$zipPath = Join-Path $buildPath "$archiveName.zip"
$infoJsonPath = Join-Path $buildPath "info.json"

if (-not (Test-Path -LiteralPath $DivinePath)) {
    $resolvedCommand = Get-Command $DivinePath -ErrorAction SilentlyContinue
    if (-not $resolvedCommand) {
        throw "Divine executable was not found: '$DivinePath'."
    }
    $DivinePath = $resolvedCommand.Source
}

if (-not (Test-Path -LiteralPath $modPath)) {
    throw "Mod folder was not found: '$modPath'."
}

if (-not (Test-Path -LiteralPath $metaPath)) {
    throw "meta.lsx was not found: '$metaPath'."
}

if (-not (Test-Path -LiteralPath (Join-Path $modPath "Localization\\Russian\\russian.xml"))) {
    throw "Localization file was not found under '$modPath'."
}

$resolvedVersion64 = Get-ModuleInfoVersion64 -MetaPath $metaPath
if ($VersionTag) {
    $resolvedVersion64 = Convert-VersionTagToVersion64 -Tag $VersionTag -RepoPath $workspacePath
    Set-ModuleInfoVersion64 -MetaPath $metaPath -Version64 $resolvedVersion64
}

New-Item -ItemType Directory -Path $buildPath -Force | Out-Null

foreach ($path in @($stagingPath, $tempPackagePath, $packagePath, $zipPath, $infoJsonPath)) {
    if (Test-Path -LiteralPath $path) {
        if ((Get-Item -LiteralPath $path).PSIsContainer) {
            Remove-Item -LiteralPath $path -Recurse -Force
        } else {
            Remove-Item -LiteralPath $path -Force
        }
    }
}

if (Test-Path -LiteralPath $stagingRoot) {
    Remove-Item -LiteralPath $stagingRoot -Recurse -Force
}

New-Item -ItemType Directory -Path $stagingPath -Force | Out-Null
Copy-Item -LiteralPath $modsPath -Destination $stagingPath -Recurse

Write-Host "[build.ps1] Staged source tree:"
Get-ChildItem -Recurse $stagingPath | Select-Object FullName, Length | Format-Table -AutoSize

if (Test-Path -LiteralPath $tempPackagePath) {
    Remove-Item -LiteralPath $tempPackagePath -Force
}

# CI quirk: Divine can occasionally emit a broken ~48-byte package for some source roots.
# Mitigation: try staged/mods/workspace sources and accept only outputs that look valid by size.
$packageAttempts = @(
    [ordered]@{ Name = "staging-root"; Source = $stagingPath },
    [ordered]@{ Name = "mods-root"; Source = $modsPath },
    [ordered]@{ Name = "workspace-root"; Source = $workspacePath }
)

$successfulAttempt = $null
foreach ($attempt in $packageAttempts) {
    if (Test-Path -LiteralPath $tempPackagePath) {
        Remove-Item -LiteralPath $tempPackagePath -Force
    }

    Write-Host "[build.ps1] Trying Divine source '$($attempt.Name)': $($attempt.Source)"
    & $DivinePath -a create-package -g bg3 -s $attempt.Source -d $tempPackagePath

    if (-not (Test-Path -LiteralPath $tempPackagePath)) {
        Write-Host "[build.ps1] No package created for attempt '$($attempt.Name)'."
        continue
    }

    $attemptPackage = Get-Item -LiteralPath $tempPackagePath
    Write-Host "[build.ps1] Attempt '$($attempt.Name)' produced $($attemptPackage.Length) bytes."

    if ($attemptPackage.Length -ge 1024) {
        $successfulAttempt = $attempt
        break
    }
}

if (-not $successfulAttempt) {
    $lastSize = "missing"
    if (Test-Path -LiteralPath $tempPackagePath) {
        $lastSize = (Get-Item -LiteralPath $tempPackagePath).Length
    }
    throw "Package looks invalid after all attempts. Last output '$tempPackagePath' size: $lastSize bytes."
}

Move-Item -LiteralPath $tempPackagePath -Destination $packagePath

if (-not (Test-Path -LiteralPath $packagePath)) {
    throw "Package was not created."
}

$packageFile = Get-Item -LiteralPath $packagePath
Write-Host "[build.ps1] Using package from attempt '$($successfulAttempt.Name)'."

$packageMd5 = (Get-FileHash -LiteralPath $packagePath -Algorithm MD5).Hash.ToLowerInvariant()
$createdAt = (Get-Date).ToString("o")

$infoJson = [ordered]@{
    Mods = @(
        [ordered]@{
            Author = $ModAuthor
            Name = $ModName
            Folder = $ModFolder
            Version = [string]$resolvedVersion64
            Description = $ModDescription
            UUID = $ModUuid
            Created = $createdAt
            Dependencies = @($DependencyUuid)
            Group = $ModGroup
        }
    )
    MD5 = $packageMd5
} | ConvertTo-Json -Depth 4

Set-Content -LiteralPath $infoJsonPath -Value $infoJson -Encoding utf8
Compress-Archive -LiteralPath @($packagePath, $infoJsonPath) -DestinationPath $zipPath -CompressionLevel Optimal

if (-not (Test-Path -LiteralPath $zipPath)) {
    throw "ZIP archive was not created."
}

Get-ChildItem -LiteralPath $packagePath, $infoJsonPath, $zipPath |
    Select-Object FullName, Length, LastWriteTime
