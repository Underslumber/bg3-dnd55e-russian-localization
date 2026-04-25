param(
    [Parameter(Mandatory = $true)]
    [string]$VersionTag,

    [string]$Workspace = (Get-Location).Path,
    [string]$Bg3ToolPath = "",
    [string]$ModFolder = "DnD 5.5e AIO Russian",
    [string]$ProjectName = "DnD 5.5e All-in-One BEYOND Russian Localization",
    [UInt64]$ModPublishHandle = 5965149,
    [UInt64]$DependencyPublishHandle = 4419649,
    [int]$CliTimeoutSeconds = 120,
    [int]$TimeoutSeconds = 900,
    [string]$ModioApiBase = "",
    [int]$ModioGameId = 0,
    [int]$ModioModId = 0,
    [string[]]$ModioPlatforms = @(),
    [int]$ModioFinalizeTimeoutSeconds = 900,

    [switch]$UseGuiFallback,
    [switch]$NoGuiFallback,
    [switch]$SkipModioApiFinalize,
    [switch]$SkipAuthCheck,
    [switch]$WhatIf,
    [switch]$KeepStaging
)

$ErrorActionPreference = "Stop"

function Resolve-FullPath {
    param([string]$Path)
    return [System.IO.Path]::GetFullPath($Path)
}

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
        throw "Version tag '$Tag' is invalid. Expected format: vX.Y.Z or vX.Y.Z-suffix."
    }

    $baseVersion = $Matches.base
    $suffix = $Matches.suffix
    $parts = $baseVersion.Split(".")
    $numbers = @(0, 0, 0, 0)
    for ($i = 0; $i -lt $parts.Length; $i++) {
        $numbers[$i] = [int]$parts[$i]
    }

    if ($suffix) {
        $matchingTags = @()
        try {
            $matchingTags = @(
                git -C (Resolve-FullPath $RepoPath) tag --list "v$baseVersion-*" 2>$null |
                    Where-Object { $_ -and $_ -ne $Tag }
            )
        } catch {
            $matchingTags = @()
        }
        $numbers[3] = $matchingTags.Count + 1
    }

    return ([int64]$numbers[0] -shl 55) -bor ([int64]$numbers[1] -shl 47) -bor ([int64]$numbers[2] -shl 31) -bor [int64]$numbers[3]
}

function Convert-VersionTagToModioVersion {
    param(
        [string]$Tag,
        [string]$RepoPath
    )

    $normalized = $Tag
    if ($normalized.StartsWith("v")) {
        $normalized = $normalized.Substring(1)
    }

    if ($normalized -notmatch '^(?<base>\d+\.\d+\.\d+)(?:-(?<suffix>[0-9A-Za-z][0-9A-Za-z.-]*))?$') {
        throw "Version tag '$Tag' is invalid. Expected format: vX.Y.Z or vX.Y.Z-suffix."
    }

    $baseVersion = $Matches.base
    $suffix = $Matches.suffix
    $parts = $baseVersion.Split(".")
    $build = 0

    if ($suffix) {
        $matchingTags = @()
        try {
            $matchingTags = @(
                git -C (Resolve-FullPath $RepoPath) tag --list "v$baseVersion-*" 2>$null |
                    Where-Object { $_ -and $_ -ne $Tag }
            )
        } catch {
            $matchingTags = @()
        }
        $build = $matchingTags.Count + 1
    }

    return "{0}.{1}.{2}.{3}" -f $parts[0], $parts[1], $parts[2], $build
}

function Resolve-ModioPlatforms {
    param([string[]]$Value)

    if ($Value -and $Value.Count -gt 0) {
        return @($Value | ForEach-Object { $_.Trim() } | Where-Object { $_ })
    }

    if ($env:MODIO_PLATFORMS) {
        return @($env:MODIO_PLATFORMS -split "," | ForEach-Object { $_.Trim() } | Where-Object { $_ })
    }

    return @("windows", "mac", "xboxseriesx", "ps5")
}

function Get-MetaAttributeValue {
    param(
        [xml]$Meta,
        [string]$XPath
    )

    $node = $Meta.SelectSingleNode($XPath)
    if (-not $node) {
        return $null
    }
    return $node.value
}

function Set-ModuleInfoVersion64 {
    param(
        [string]$MetaPath,
        [int64]$Version64
    )

    $utf8Encoding = [System.Text.UTF8Encoding]::new($false)
    $metaContent = [System.IO.File]::ReadAllText($MetaPath, $utf8Encoding)
    $moduleInfoPattern = '(?s)(<node id="ModuleInfo">\s*(?:(?!<children>).)*?<attribute id="Version64" type="int64" value=")\d+("/>)'
    $match = [System.Text.RegularExpressions.Regex]::Match($metaContent, $moduleInfoPattern)
    if (-not $match.Success) {
        throw "ModuleInfo/Version64 attribute was not found in '$MetaPath'."
    }

    $updatedMetaContent =
        $metaContent.Substring(0, $match.Index) +
        $match.Groups[1].Value +
        $Version64 +
        $match.Groups[2].Value +
        $metaContent.Substring($match.Index + $match.Length)

    [System.IO.File]::WriteAllText($MetaPath, $updatedMetaContent, $utf8Encoding)
}

function Test-ToolkitAuthState {
    param([string]$ToolkitPath)

    $candidateRoots = @(
        (Join-Path $env:LOCALAPPDATA "Larian Studios\Glasses"),
        (Join-Path $env:LOCALAPPDATA "Larian Studios\Baldur's Gate 3 Toolkit"),
        (Split-Path -Parent $ToolkitPath)
    ) | Where-Object { $_ -and (Test-Path -LiteralPath $_) }

    $authSignals = @()
    foreach ($root in $candidateRoots) {
        $authSignals += Get-ChildItem -LiteralPath $root -Recurse -File -ErrorAction SilentlyContinue |
            Where-Object {
                $_.Name -match '(auth|token|modio|mod\.io|larian|network)' -or
                $_.FullName -match '(ModIo|modio|mod\.io|LarianNet)'
            } |
            Select-Object -First 1
    }

    return ($authSignals.Count -gt 0)
}

function Copy-CleanDirectory {
    param(
        [string]$Source,
        [string]$Destination
    )

    if (Test-Path -LiteralPath $Destination) {
        Remove-Item -LiteralPath $Destination -Recurse -Force
    }

    New-Item -ItemType Directory -Path (Split-Path -Parent $Destination) -Force | Out-Null
    Copy-Item -LiteralPath $Source -Destination $Destination -Recurse -Force
}

function Invoke-ToolkitCliPublish {
    param(
        [string]$ToolPath,
        [string]$Project,
        [int]$Timeout
    )

    $arguments = @(
        "-project", $Project,
        "-publish"
    )

    Write-Host "[publish-modio] Trying Toolkit CLI publish: $ToolPath $($arguments -join ' ')"
    $process = Start-Process -FilePath $ToolPath -ArgumentList $arguments -PassThru -WindowStyle Normal
    if (-not $process.WaitForExit($Timeout * 1000)) {
        try {
            $process.Kill()
        } catch {
            Write-Warning "[publish-modio] Failed to stop timed out Toolkit process: $($_.Exception.Message)"
        }
        throw "Toolkit CLI publish timed out after $Timeout seconds."
    }

    if ($process.ExitCode -ne 0) {
        throw "Toolkit CLI publish exited with code $($process.ExitCode)."
    }
}

$workspacePath = Resolve-FullPath $Workspace
$modPath = Join-Path $workspacePath "Mods\$ModFolder"
$metaPath = Join-Path $modPath "meta.lsx"
$localizationPath = Join-Path $modPath "Localization\Russian\russian.xml"
$projectPath = Join-Path $workspacePath "Projects"
$projectMetaPath = Join-Path $projectPath "meta.lsx"
$thumbnailPath = Join-Path $projectPath "thumbnail.png"

if (-not $Bg3ToolPath) {
    $Bg3ToolPath = $env:BG3TOOL_PATH
}
if (-not $Bg3ToolPath) {
    $Bg3ToolPath = "C:\Program Files (x86)\Steam\steamapps\common\Baldurs Gate 3 Toolkit\Glasses.exe"
}
$resolvedBg3ToolPath = Resolve-FullPath $Bg3ToolPath

foreach ($requiredPath in @($metaPath, $localizationPath, $projectMetaPath, $thumbnailPath)) {
    if (-not (Test-Path -LiteralPath $requiredPath)) {
        throw "Required mod.io publish input was not found: '$requiredPath'."
    }
}

if (-not (Test-Path -LiteralPath $resolvedBg3ToolPath)) {
    throw "BG3 Toolkit executable was not found: '$resolvedBg3ToolPath'. Set BG3TOOL_PATH or pass -Bg3ToolPath."
}

[xml]$metaXml = Get-Content -LiteralPath $metaPath -Raw
$actualModPublishHandle = Get-MetaAttributeValue -Meta $metaXml -XPath '//node[@id="ModuleInfo"]/attribute[@id="PublishHandle"]'
$actualDependencyPublishHandle = Get-MetaAttributeValue -Meta $metaXml -XPath '//node[@id="Dependencies"]//node[@id="ModuleShortDesc"]/attribute[@id="PublishHandle"]'

if ([UInt64]$actualModPublishHandle -ne $ModPublishHandle) {
    throw "Unexpected mod PublishHandle '$actualModPublishHandle'. Expected '$ModPublishHandle'."
}

if ([UInt64]$actualDependencyPublishHandle -ne $DependencyPublishHandle) {
    throw "Unexpected dependency PublishHandle '$actualDependencyPublishHandle'. Expected '$DependencyPublishHandle'."
}

if (-not $SkipAuthCheck -and -not (Test-ToolkitAuthState -ToolkitPath $resolvedBg3ToolPath)) {
    throw "Could not detect a preconfigured BG3 Toolkit/Larian/mod.io session on this runner. Open the Toolkit once and authenticate before publishing."
}

$resolvedVersion64 = Convert-VersionTagToVersion64 -Tag $VersionTag -RepoPath $workspacePath
$modioExpectedVersion = Convert-VersionTagToModioVersion -Tag $VersionTag -RepoPath $workspacePath
$stagingRoot = Join-Path $env:TEMP "bg3-dnd55e-russian-localization-modio"
$stagingPath = Join-Path $stagingRoot "workspace"

if (Test-Path -LiteralPath $stagingRoot) {
    Remove-Item -LiteralPath $stagingRoot -Recurse -Force
}

New-Item -ItemType Directory -Path $stagingPath -Force | Out-Null
Copy-Item -LiteralPath (Join-Path $workspacePath "Mods") -Destination $stagingPath -Recurse -Force
Copy-Item -LiteralPath $projectPath -Destination $stagingPath -Recurse -Force

$stagedMetaPath = Join-Path $stagingPath "Mods\$ModFolder\meta.lsx"
Set-ModuleInfoVersion64 -MetaPath $stagedMetaPath -Version64 $resolvedVersion64

$defaultGameModsRoot = Join-Path $env:LOCALAPPDATA "Larian Studios\Baldur's Gate 3\Mods"
$gameModsRoot = if ($env:BG3_MODS_PATH) { Resolve-FullPath $env:BG3_MODS_PATH } else { $defaultGameModsRoot }
$toolkitProjectsRoot = if ($env:BG3_TOOLKIT_PROJECTS_PATH) { Resolve-FullPath $env:BG3_TOOLKIT_PROJECTS_PATH } else { Join-Path $gameModsRoot "Projects" }

$stagedModPath = Join-Path $stagingPath "Mods\$ModFolder"
$stagedProjectPath = Join-Path $stagingPath "Projects"
$targetModPath = Join-Path $gameModsRoot $ModFolder
$targetProjectPath = Join-Path $toolkitProjectsRoot $ProjectName
$resolvedModioPlatforms = Resolve-ModioPlatforms -Value $ModioPlatforms

if (-not $ModioApiBase) {
    $ModioApiBase = $env:MODIO_API_BASE
}
if (-not $ModioApiBase) {
    $ModioApiBase = "https://g-6715.modapi.io/v1"
}
if (-not $ModioGameId) {
    if ($env:MODIO_GAME_ID) {
        $ModioGameId = [int]$env:MODIO_GAME_ID
    } else {
        $ModioGameId = 6715
    }
}
if (-not $ModioModId) {
    if ($env:MODIO_MOD_ID) {
        $ModioModId = [int]$env:MODIO_MOD_ID
    } else {
        $ModioModId = [int]$ModPublishHandle
    }
}

Write-Host "[publish-modio] VersionTag=$VersionTag Version64=$resolvedVersion64"
Write-Host "[publish-modio] mod.io expected version=$modioExpectedVersion"
Write-Host "[publish-modio] Toolkit=$resolvedBg3ToolPath"
Write-Host "[publish-modio] Mod target=$targetModPath"
Write-Host "[publish-modio] Project target=$targetProjectPath"
Write-Host "[publish-modio] mod.io ApiBase=$ModioApiBase GameId=$ModioGameId ModId=$ModioModId Platforms=$($resolvedModioPlatforms -join ',')"

if ($WhatIf) {
    $authMessage = if ($SkipAuthCheck) { "auth check skipped" } else { "auth signal validated" }
    Write-Host "[publish-modio] WhatIf completed: inputs, publish handles, $authMessage, and staging metadata were validated."
    if (-not $KeepStaging -and (Test-Path -LiteralPath $stagingRoot)) {
        Remove-Item -LiteralPath $stagingRoot -Recurse -Force
    }
    exit 0
}

Copy-CleanDirectory -Source $stagedModPath -Destination $targetModPath
Copy-CleanDirectory -Source $stagedProjectPath -Destination $targetProjectPath

$uploadedAfter = Get-Date
$cliSucceeded = $false
if (-not $UseGuiFallback) {
    try {
        Invoke-ToolkitCliPublish -ToolPath $resolvedBg3ToolPath -Project $ProjectName -Timeout $CliTimeoutSeconds
        $cliSucceeded = $true
    } catch {
        Write-Warning "[publish-modio] Toolkit CLI publish failed: $($_.Exception.Message)"
        if ($NoGuiFallback) {
            throw
        }
    }
}

if (-not $cliSucceeded) {
    & (Join-Path $PSScriptRoot "publish-modio-ui.ps1") `
        -Bg3ToolPath $resolvedBg3ToolPath `
        -ProjectName $ProjectName `
        -ProjectPath $targetProjectPath `
        -TimeoutSeconds $TimeoutSeconds
}

if (-not $SkipModioApiFinalize) {
    $modioAccessToken = $env:MODIO_ACCESS_TOKEN
    if (-not $modioAccessToken) {
        throw "MODIO_ACCESS_TOKEN is required after Toolkit upload. Set it as a GitHub Environment secret or pass -SkipModioApiFinalize for manual finalization."
    }

    & (Join-Path $PSScriptRoot "finalize-modio-file.ps1") `
        -ApiBase $ModioApiBase `
        -GameId $ModioGameId `
        -ModId $ModioModId `
        -AccessToken $modioAccessToken `
        -ExpectedVersion $modioExpectedVersion `
        -UploadedAfter $uploadedAfter `
        -Platforms $resolvedModioPlatforms `
        -TimeoutSeconds $ModioFinalizeTimeoutSeconds
} else {
    Write-Host "[publish-modio] Skipping mod.io API finalization by request."
}

if (-not $KeepStaging -and (Test-Path -LiteralPath $stagingRoot)) {
    Remove-Item -LiteralPath $stagingRoot -Recurse -Force
}
