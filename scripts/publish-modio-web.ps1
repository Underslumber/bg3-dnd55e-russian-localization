param(
    [int64]$FileId = 0,
    [string]$BrowserPath = "",
    [string]$ModSlug = "dnd-55e-all-in-one-beyond-russian-localization",
    [string]$GameSlug = "baldursgate3",
    [string[]]$Platforms = @(),
    [int]$DebugPort = 9222,
    [int]$TimeoutSeconds = 120,
    [switch]$WhatIf
)

$ErrorActionPreference = "Stop"

function Resolve-BrowserPath {
    if ($BrowserPath) {
        return [IO.Path]::GetFullPath($BrowserPath)
    }
    if ($env:MODIO_BROWSER_PATH) {
        return [IO.Path]::GetFullPath($env:MODIO_BROWSER_PATH)
    }

    foreach ($candidate in @(
        "C:\Program Files\Yandex\YandexBrowser\Application\browser.exe",
        "C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"
    )) {
        if (Test-Path -LiteralPath $candidate) {
            return $candidate
        }
    }
    throw "A Chromium browser was not found. Set MODIO_BROWSER_PATH."
}

function Resolve-NodePath {
    $node = Get-Command node.exe -ErrorAction SilentlyContinue
    if ($node) {
        return $node.Source
    }

    $runnerRoot = if ($env:RUNNER_ROOT) { $env:RUNNER_ROOT } else { "C:\actions-runner" }
    $candidate = Get-ChildItem -LiteralPath (Join-Path $runnerRoot "externals") -Directory -Filter "node*" -ErrorAction SilentlyContinue |
        Sort-Object Name -Descending |
        ForEach-Object { Join-Path $_.FullName "bin\node.exe" } |
        Where-Object { Test-Path -LiteralPath $_ } |
        Select-Object -First 1
    if (-not $candidate) {
        throw "Node.js was not found in PATH or the GitHub Actions runner externals directory."
    }
    return $candidate
}

function Test-Cdp {
    try {
        $null = Invoke-RestMethod -Uri "http://127.0.0.1:$DebugPort/json/version" -TimeoutSec 3
        return $true
    } catch {
        return $false
    }
}

$resolvedBrowserPath = Resolve-BrowserPath
if (-not (Test-Path -LiteralPath $resolvedBrowserPath)) {
    throw "Browser executable was not found: '$resolvedBrowserPath'."
}
$nodePath = Resolve-NodePath
$nodeScript = Join-Path $PSScriptRoot "publish-modio-web.mjs"
if (-not (Test-Path -LiteralPath $nodeScript)) {
    throw "mod.io browser automation script was not found: '$nodeScript'."
}

$adminUrl = "https://mod.io/g/$GameSlug/m/$ModSlug/admin/settings#files"
if (-not (Test-Cdp)) {
    $browserProcessName = [IO.Path]::GetFileNameWithoutExtension($resolvedBrowserPath)
    Get-Process -Name $browserProcessName -ErrorAction SilentlyContinue | Stop-Process -Force
    Start-Sleep -Seconds 2
    Start-Process -FilePath $resolvedBrowserPath -ArgumentList @(
        "--remote-debugging-port=$DebugPort",
        "--remote-allow-origins=*",
        $adminUrl
    ) | Out-Null

    $deadline = (Get-Date).AddSeconds(30)
    do {
        Start-Sleep -Seconds 1
        if (Test-Cdp) {
            break
        }
    } while ((Get-Date) -lt $deadline)

    if (-not (Test-Cdp)) {
        throw "Browser CDP endpoint did not start on port $DebugPort."
    }
}

$resolvedPlatforms = if ($Platforms -and $Platforms.Count -gt 0) {
    @($Platforms | ForEach-Object { $_.Trim() } | Where-Object { $_ })
} else {
    @("windows", "mac", "xboxseriesx", "ps5")
}

$arguments = @(
    $nodeScript,
    "--file-id", "$FileId",
    "--mod-slug", $ModSlug,
    "--game-slug", $GameSlug,
    "--platforms", ($resolvedPlatforms -join ","),
    "--debug-port", "$DebugPort",
    "--timeout-seconds", "$TimeoutSeconds",
    "--what-if", $WhatIf.ToString().ToLowerInvariant()
)

$output = & $nodePath @arguments
if ($LASTEXITCODE -ne 0) {
    throw "mod.io browser finalization failed with exit code $LASTEXITCODE."
}
$resultText = @($output | Where-Object { $_ })[-1]
$result = $resultText | ConvertFrom-Json
Write-Host "[publish-modio-web] $resultText"
if ($result.status -notin @("published", "already_live", "whatif")) {
    throw "Unexpected mod.io browser finalization status: '$($result.status)'."
}
