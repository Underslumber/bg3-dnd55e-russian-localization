param(
    [string]$GamePath = "",
    [string]$Workspace = ""
)

$ErrorActionPreference = "Stop"

$modFolderName = "DnD 5.5e AIO Russian"

function Get-NormalizedPath {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Path
    )

    return [System.IO.Path]::GetFullPath($Path)
}

function Get-WorkspacePath {
    param(
        [string]$ExplicitWorkspace
    )

    if ($ExplicitWorkspace) {
        return Get-NormalizedPath -Path $ExplicitWorkspace
    }

    if ($PSScriptRoot) {
        return Get-NormalizedPath -Path (Join-Path $PSScriptRoot "..")
    }

    return Get-NormalizedPath -Path (Get-Location).Path
}

function Get-SteamRootFromRegistry {
    $registryPaths = @(
        "HKCU:\Software\Valve\Steam",
        "HKLM:\SOFTWARE\WOW6432Node\Valve\Steam",
        "HKLM:\SOFTWARE\Valve\Steam"
    )

    foreach ($registryPath in $registryPaths) {
        if (-not (Test-Path -LiteralPath $registryPath)) {
            continue
        }

        $steamKey = Get-ItemProperty -Path $registryPath
        foreach ($propertyName in @("SteamPath", "InstallPath")) {
            $propertyValue = $steamKey.$propertyName
            if (-not [string]::IsNullOrWhiteSpace($propertyValue)) {
                $resolved = Get-NormalizedPath -Path $propertyValue
                if (Test-Path -LiteralPath $resolved) {
                    return $resolved
                }
            }
        }
    }

    throw "Failed to detect the Steam path from the Windows registry."
}

function Get-SteamLibraryPaths {
    param(
        [Parameter(Mandatory = $true)]
        [string]$SteamRoot
    )

    $libraryFile = Join-Path $SteamRoot "steamapps\libraryfolders.vdf"
    if (-not (Test-Path -LiteralPath $libraryFile)) {
        throw "Steam library file was not found: '$libraryFile'."
    }

    $libraries = [System.Collections.Generic.List[string]]::new()
    $libraries.Add($SteamRoot)

    foreach ($line in Get-Content -LiteralPath $libraryFile) {
        if ($line -match '^\s*"path"\s*"(?<path>.+)"\s*$' -or $line -match '^\s*"\d+"\s*"(?<path>.+)"\s*$') {
            $rawPath = $Matches.path.Replace("\\", "\")
            $resolved = Get-NormalizedPath -Path $rawPath
            if (-not $libraries.Contains($resolved)) {
                $libraries.Add($resolved)
            }
        }
    }

    return $libraries
}

function Resolve-Bg3GamePath {
    param(
        [string]$ExplicitGamePath
    )

    if ($ExplicitGamePath) {
        $resolvedGamePath = Get-NormalizedPath -Path $ExplicitGamePath
        Write-Host "[link-bg3-dev-folders] Using game path from parameter: $resolvedGamePath"
        return $resolvedGamePath
    }

    $steamRoot = Get-SteamRootFromRegistry
    Write-Host "[link-bg3-dev-folders] Found Steam root: $steamRoot"

    $libraryPaths = Get-SteamLibraryPaths -SteamRoot $steamRoot
    foreach ($libraryPath in $libraryPaths) {
        $candidate = Join-Path $libraryPath "steamapps\common\Baldurs Gate 3"
        if (-not (Test-Path -LiteralPath $candidate)) {
            continue
        }

        $modsDirectory = Join-Path $candidate "Data\Mods"
        $projectsDirectory = Join-Path $candidate "Data\Projects"
        if ((Test-Path -LiteralPath $modsDirectory) -and (Test-Path -LiteralPath $projectsDirectory)) {
            Write-Host "[link-bg3-dev-folders] Found BG3 install: $candidate"
            return $candidate
        }
    }

    throw "Failed to find a Baldur's Gate 3 installation in Steam libraries."
}

function Assert-DirectoryExists {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Path,
        [Parameter(Mandatory = $true)]
        [string]$Description
    )

    if (-not (Test-Path -LiteralPath $Path)) {
        throw ("{0} was not found: '{1}'." -f $Description, $Path)
    }

    $item = Get-Item -LiteralPath $Path -Force
    if (-not $item.PSIsContainer) {
        throw ("{0} must be a directory: '{1}'." -f $Description, $Path)
    }
}

function Get-LinkTargetPath {
    param(
        [Parameter(Mandatory = $true)]
        [System.IO.FileSystemInfo]$Item
    )

    if (-not $Item.LinkTarget) {
        return $null
    }

    if ([System.IO.Path]::IsPathRooted($Item.LinkTarget)) {
        return Get-NormalizedPath -Path $Item.LinkTarget
    }

    $combined = Join-Path $Item.DirectoryName $Item.LinkTarget
    return Get-NormalizedPath -Path $combined
}

function New-DirectorySymbolicLink {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Path,
        [Parameter(Mandatory = $true)]
        [string]$Target
    )

    try {
        New-Item -ItemType SymbolicLink -Path $Path -Target $Target | Out-Null
    } catch {
        $exceptionMessage = $_.Exception.Message
        $accessDenied = $_.Exception -is [System.UnauthorizedAccessException] -or $exceptionMessage -match "privilege|not held|access.*denied|administrator"
        if ($accessDenied) {
            throw "Failed to create symbolic link '$Path' -> '$Target'. Symlink permissions are required (Developer Mode or elevated shell)."
        }

        throw
    }
}

function Ensure-DirectorySymbolicLink {
    param(
        [Parameter(Mandatory = $true)]
        [string]$LinkPath,
        [Parameter(Mandatory = $true)]
        [string]$TargetPath,
        [Parameter(Mandatory = $true)]
        [string]$Label
    )

    if (-not (Test-Path -LiteralPath $LinkPath)) {
        New-DirectorySymbolicLink -Path $LinkPath -Target $TargetPath
        Write-Host ("[link-bg3-dev-folders] {0}: symbolic link created" -f $Label)
        return
    }

    $existingItem = Get-Item -LiteralPath $LinkPath -Force
    $isReparsePoint = ($existingItem.Attributes -band [System.IO.FileAttributes]::ReparsePoint) -ne 0
    if (-not $isReparsePoint) {
        throw ("{0}: path already exists and is not a link: '{1}'." -f $Label, $LinkPath)
    }

    $currentTarget = Get-LinkTargetPath -Item $existingItem
    if (-not $currentTarget) {
        throw ("{0}: failed to resolve the target of the existing link: '{1}'." -f $Label, $LinkPath)
    }

    if ($currentTarget -ieq $TargetPath) {
        Write-Host ("[link-bg3-dev-folders] {0}: link already points to the expected directory" -f $Label)
        return
    }

    Remove-Item -LiteralPath $LinkPath -Force
    New-DirectorySymbolicLink -Path $LinkPath -Target $TargetPath
    Write-Host ("[link-bg3-dev-folders] {0}: link updated" -f $Label)
}

$workspacePath = Get-WorkspacePath -ExplicitWorkspace $Workspace
Write-Host "[link-bg3-dev-folders] Workspace: $workspacePath"

$modsSourceRoot = Join-Path $workspacePath "Mods"
$modsSourcePath = Join-Path $modsSourceRoot $modFolderName
$projectsSourcePath = Join-Path $workspacePath "Projects"

Assert-DirectoryExists -Path $modsSourceRoot -Description "Mods source root"
Assert-DirectoryExists -Path $modsSourcePath -Description "Mod source directory"
Assert-DirectoryExists -Path $projectsSourcePath -Description "Projects source directory"

$resolvedGamePath = Get-NormalizedPath -Path (Resolve-Bg3GamePath -ExplicitGamePath $GamePath)
$dataPath = Join-Path $resolvedGamePath "Data"
$modsTargetRoot = Join-Path $dataPath "Mods"
$projectsTargetRoot = Join-Path $dataPath "Projects"

Assert-DirectoryExists -Path $resolvedGamePath -Description "Game directory"
Assert-DirectoryExists -Path $dataPath -Description "Data directory"
Assert-DirectoryExists -Path $modsTargetRoot -Description "Data\\Mods directory"
Assert-DirectoryExists -Path $projectsTargetRoot -Description "Data\\Projects directory"

$modsLinkPath = Join-Path $modsTargetRoot $modFolderName
$projectsLinkPath = Join-Path $projectsTargetRoot $modFolderName

Ensure-DirectorySymbolicLink -LinkPath $modsLinkPath -TargetPath $modsSourcePath -Label "Mods"
Ensure-DirectorySymbolicLink -LinkPath $projectsLinkPath -TargetPath $projectsSourcePath -Label "Projects"

Write-Host ""
Write-Host "[link-bg3-dev-folders] Done:"
Write-Host "  Mods source    : $modsSourcePath"
Write-Host "  Mods link      : $modsLinkPath"
Write-Host "  Projects source: $projectsSourcePath"
Write-Host "  Projects link  : $projectsLinkPath"
