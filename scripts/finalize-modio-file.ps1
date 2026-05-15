param(
    [string]$ApiBase = "",
    [int]$GameId = 0,
    [int]$ModId = 0,
    [string]$AccessToken = "",
    [string]$ExpectedVersion = "",
    [string]$Changelog = "",
    [datetime]$UploadedAfter = (Get-Date).AddHours(-2),
    [string[]]$Platforms = @(),
    [int]$TimeoutSeconds = 900,
    [switch]$WhatIf
)

$ErrorActionPreference = "Stop"

function Resolve-Setting {
    param(
        [string]$Value,
        [string]$EnvironmentName,
        [string]$DefaultValue
    )

    if ($Value) {
        return $Value
    }

    $environmentValue = [Environment]::GetEnvironmentVariable($EnvironmentName)
    if ($environmentValue) {
        return $environmentValue
    }

    return $DefaultValue
}

function ConvertTo-UnixTimeSeconds {
    param([datetime]$Value)

    $epoch = [datetime]::new(1970, 1, 1, 0, 0, 0, [DateTimeKind]::Utc)
    return [int64][Math]::Floor(($Value.ToUniversalTime() - $epoch).TotalSeconds)
}

function Convert-VersionTagToModioVersion {
    param(
        [string]$VersionTag,
        [string]$RepoPath
    )

    $normalized = $VersionTag
    if ($normalized.StartsWith("v")) {
        $normalized = $normalized.Substring(1)
    }

    if ($normalized -notmatch '^(?<base>\d+\.\d+\.\d+)(?:-(?<suffix>[0-9A-Za-z][0-9A-Za-z.-]*))?$') {
        return $VersionTag
    }

    $baseVersion = $Matches.base
    $suffix = $Matches.suffix
    $parts = $baseVersion.Split(".")
    $build = 0

    if ($suffix) {
        $matchingTags = @()
        try {
            $matchingTags = @(
                git -C $RepoPath tag --list "v$baseVersion-*" 2>$null |
                    Where-Object { $_ -and $_ -ne $VersionTag }
            )
        } catch {
            $matchingTags = @()
        }
        $build = $matchingTags.Count + 1
    }

    return "{0}.{1}.{2}.{3}" -f $parts[0], $parts[1], $parts[2], $build
}

function Invoke-ModioRequest {
    param(
        [string]$Method,
        [string]$Uri,
        [hashtable]$Payload = $null
    )

    $headers = @{
        Authorization = "Bearer $script:AccessToken"
        Accept = "application/json"
    }

    try {
        if ($Payload) {
            $body = @{
                input_json = ($Payload | ConvertTo-Json -Compress -Depth 10)
            }
            return Invoke-RestMethod -Method $Method -Uri $Uri -Headers $headers -ContentType "application/x-www-form-urlencoded" -Body $body
        }

        return Invoke-RestMethod -Method $Method -Uri $Uri -Headers $headers
    } catch {
        $statusCode = $null
        $responseBody = ""
        if ($_.Exception.Response) {
            $statusCode = [int]$_.Exception.Response.StatusCode
            try {
                $reader = New-Object System.IO.StreamReader($_.Exception.Response.GetResponseStream())
                $responseBody = $reader.ReadToEnd()
            } catch {
                $responseBody = ""
            }
        }

        $message = "mod.io API request failed: $Method $Uri"
        if ($statusCode) {
            $message = "$message (HTTP $statusCode)"
        }
        if ($responseBody) {
            $message = "$message $responseBody"
        }
        throw $message
    }
}

function Get-ModioFiles {
    $filesById = @{}
    $platformStatusFilters = @("", "pending_only", "approved_only", "live_and_pending", "live_and_approved")

    foreach ($platformStatus in $platformStatusFilters) {
        $uri = "{0}/games/{1}/mods/{2}/files" -f $script:ApiBase, $script:GameId, $script:ModId
        if ($platformStatus) {
            $uri = "$uri?platform_status=$([Uri]::EscapeDataString($platformStatus))"
        }

        try {
            $response = Invoke-ModioRequest -Method "GET" -Uri $uri
        } catch {
            if ($platformStatus) {
                Write-Host "[finalize-modio-file] Optional platform_status=$platformStatus file view is unavailable; continuing."
                continue
            }
            throw
        }
        $files = @()
        if ($response.PSObject.Properties.Name -contains "data") {
            $files = @($response.data)
        } else {
            $files = @($response)
        }

        foreach ($file in $files) {
            if ($file -and ($file.PSObject.Properties.Name -contains "id")) {
                $filesById[[string]$file.id] = $file
            }
        }
    }

    return @($filesById.Values)
}

function Find-NewestUploadedFile {
    param([int64]$UploadedAfterUnix)

    $files = @(Get-ModioFiles)
    $candidate = $files |
        Where-Object { $_.date_added -ge $UploadedAfterUnix } |
        Sort-Object -Property date_added -Descending |
        Select-Object -First 1

    return $candidate
}

function Get-ScanStatusName {
    param([int]$Status)

    switch ($Status) {
        0 { return "not_scanned" }
        1 { return "scanned" }
        2 { return "scan_in_progress" }
        3 { return "file_too_large" }
        4 { return "file_not_found" }
        5 { return "scan_error" }
        default { return "unknown_$Status" }
    }
}

function Wait-ForScannedFile {
    param([int64]$UploadedAfterUnix)

    $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
    do {
        $file = Find-NewestUploadedFile -UploadedAfterUnix $UploadedAfterUnix
        if (-not $file) {
            Write-Host "[finalize-modio-file] Waiting for uploaded file after $UploadedAfter..."
            Start-Sleep -Seconds 10
            continue
        }

        $scanStatus = [int]$file.virus_status
        $virusPositive = [int]$file.virus_positive
        $scanStatusName = Get-ScanStatusName -Status $scanStatus
        Write-Host "[finalize-modio-file] File id=$($file.id) filename=$($file.filename) version=$($file.version) scan=$scanStatusName virus_positive=$virusPositive"

        if ($scanStatus -eq 1 -and $virusPositive -eq 0) {
            return $file
        }

        if ($scanStatus -in @(3, 4, 5)) {
            throw "mod.io scan failed for file id=$($file.id): $scanStatusName."
        }

        if ($virusPositive -ne 0) {
            throw "mod.io scan flagged file id=$($file.id): virus_positive=$virusPositive."
        }

        Start-Sleep -Seconds 10
    } while ((Get-Date) -lt $deadline)

    throw "Timed out after $TimeoutSeconds seconds while waiting for mod.io scan to complete."
}

function Get-ActiveModfileId {
    $uri = "{0}/games/{1}/mods/{2}" -f $script:ApiBase, $script:GameId, $script:ModId
    $mod = Invoke-ModioRequest -Method "GET" -Uri $uri
    if ($mod.PSObject.Properties.Name -contains "modfile") {
        if ($mod.modfile -is [int] -or $mod.modfile -is [long]) {
            return [int64]$mod.modfile
        }

        if ($mod.modfile -and ($mod.modfile.PSObject.Properties.Name -contains "id")) {
            return [int64]$mod.modfile.id
        }
    }

    return $null
}

function Write-FinalizeDiagnostic {
    param(
        [string]$Reason,
        [object]$File,
        [string]$Uri,
        [string[]]$Platforms,
        [string]$ErrorMessage
    )

    $diagnosticRoot = if ($env:RUNNER_TEMP) { $env:RUNNER_TEMP } elseif ($env:TEMP) { $env:TEMP } else { (Get-Location).Path }
    $diagnosticPath = Join-Path $diagnosticRoot ("modio-finalize-diagnostic-{0}.json" -f (Get-Date -Format "yyyyMMdd-HHmmss"))
    $diagnostic = [ordered]@{
        reason = $Reason
        api_base = $script:ApiBase
        game_id = $script:GameId
        mod_id = $script:ModId
        uri = $Uri
        platforms = @($Platforms)
        file = [ordered]@{
            id = $File.id
            filename = $File.filename
            version = $File.version
            virus_status = $File.virus_status
            virus_positive = $File.virus_positive
            date_added = $File.date_added
            date_updated = $File.date_updated
        }
        error = $ErrorMessage
    }

    $diagnostic | ConvertTo-Json -Depth 6 | Set-Content -LiteralPath $diagnosticPath -Encoding utf8
    Write-Host "[finalize-modio-file] Diagnostic written: $diagnosticPath"
}

function Test-ModioForbidden {
    param([object]$ErrorRecord)

    $message = ""
    if ($ErrorRecord -and $ErrorRecord.Exception) {
        $message = [string]$ErrorRecord.Exception.Message
    } elseif ($ErrorRecord) {
        $message = [string]$ErrorRecord
    }

    return ($message -match '\(HTTP 403\)')
}

function Send-ManualEnableRequest {
    param(
        [object]$File,
        [string]$ExpectedVersion,
        [string]$Reason
    )

    $modName = "mod $script:ModId"
    $modProfileUrl = ""
    try {
        $modUri = "{0}/games/{1}/mods/{2}" -f $script:ApiBase, $script:GameId, $script:ModId
        $mod = Invoke-ModioRequest -Method "GET" -Uri $modUri
        if (($mod.PSObject.Properties.Name -contains "name") -and $mod.name) {
            $modName = [string]$mod.name
        }
        if (($mod.PSObject.Properties.Name -contains "profile_url") -and $mod.profile_url) {
            $modProfileUrl = [string]$mod.profile_url
        }
    } catch {
        Write-Host "[finalize-modio-file] Could not read mod profile for the manual-enable request: $($_.Exception.Message)"
    }

    $lines = @(
        "<b>mod.io: требуется ручное включение файла</b>",
        "",
        "Мод: $modName",
        "Версия: $ExpectedVersion (файл: $($File.version))",
        "Файл: id=$($File.id), $($File.filename)",
        "",
        "Причина: $Reason",
        "Откройте mod.io и сделайте этот файл активным (live) вручную."
    )
    if ($modProfileUrl) {
        $lines += ""
        $lines += $modProfileUrl
    }
    $message = ($lines -join "`n")

    $telegramScript = Join-Path $PSScriptRoot "send-telegram-notification.ps1"
    if (-not (Test-Path -LiteralPath $telegramScript)) {
        Write-Warning "[finalize-modio-file] send-telegram-notification.ps1 not found; manual-enable request not sent."
        return
    }
    try {
        & $telegramScript -Text $message
        Write-Host "[finalize-modio-file] Manual-enable request sent to Telegram."
    } catch {
        Write-Warning "[finalize-modio-file] Telegram manual-enable request not sent (check TG_BOT_TOKEN/TG_CHAT_ID/TG_THREAD_ID): $($_.Exception.Message)"
    }
}

$ApiBase = (Resolve-Setting -Value $ApiBase -EnvironmentName "MODIO_API_BASE" -DefaultValue "https://g-6715.modapi.io/v1").TrimEnd("/")
if (-not $GameId) {
    $gameIdSetting = Resolve-Setting -Value "" -EnvironmentName "MODIO_GAME_ID" -DefaultValue "6715"
    $GameId = [int]$gameIdSetting
}
if (-not $ModId) {
    $modIdSetting = Resolve-Setting -Value "" -EnvironmentName "MODIO_MOD_ID" -DefaultValue "5965149"
    $ModId = [int]$modIdSetting
}
if (-not $AccessToken) {
    $AccessToken = [Environment]::GetEnvironmentVariable("MODIO_ACCESS_TOKEN")
}
if (-not $ExpectedVersion) {
    $ExpectedVersion = [Environment]::GetEnvironmentVariable("MODIO_EXPECTED_VERSION")
}
if (-not $ExpectedVersion -and $env:GITHUB_REF_NAME) {
    $ExpectedVersion = Convert-VersionTagToModioVersion -VersionTag $env:GITHUB_REF_NAME -RepoPath (Get-Location).Path
}
if (-not $Changelog) {
    $Changelog = [Environment]::GetEnvironmentVariable("MODIO_CHANGELOG")
}
if (-not $Platforms -or $Platforms.Count -eq 0) {
    $platformSetting = Resolve-Setting -Value "" -EnvironmentName "MODIO_PLATFORMS" -DefaultValue "windows,mac,xboxseriesx,ps5"
    $Platforms = @($platformSetting -split "," | ForEach-Object { $_.Trim() } | Where-Object { $_ })
}

if (-not $AccessToken) {
    throw "MODIO_ACCESS_TOKEN is required for mod.io API finalization."
}

$script:ApiBase = $ApiBase
$script:GameId = $GameId
$script:ModId = $ModId
$script:AccessToken = $AccessToken

$uploadedAfterUnix = ConvertTo-UnixTimeSeconds -Value $UploadedAfter

Write-Host "[finalize-modio-file] ApiBase=$ApiBase GameId=$GameId ModId=$ModId UploadedAfter=$($UploadedAfter.ToString("o"))"
Write-Host "[finalize-modio-file] Platforms=$($Platforms -join ',') ExpectedVersion=$ExpectedVersion"

$file = Wait-ForScannedFile -UploadedAfterUnix $uploadedAfterUnix

if ($WhatIf) {
    Write-Host "[finalize-modio-file] WhatIf completed: selected file id=$($file.id) filename=$($file.filename); no platform/live update was sent."
    exit 0
}

$platformUri = "{0}/games/{1}/mods/{2}/files/{3}/platforms" -f $ApiBase, $GameId, $ModId, $file.id
$platformResponse = $null
$platformApprovalFailed = $false
try {
    $platformResponse = Invoke-ModioRequest -Method "POST" -Uri $platformUri -Payload @{
        approved = @($Platforms)
    }
} catch {
    # The platform-status endpoint is not available to this publisher token (HTTP 403).
    # It is not required to make the modfile live, so record the failure and continue
    # to the live/version update instead of aborting the whole finalization.
    $platformApprovalFailed = $true
    Write-FinalizeDiagnostic -Reason "platform_status_update_failed" -File $file -Uri $platformUri -Platforms $Platforms -ErrorMessage $_.Exception.Message
    if (Test-ModioForbidden -ErrorRecord $_) {
        Write-Warning "[finalize-modio-file] Platform status update returned HTTP 403; continuing to live activation because platform approval can be unavailable to this token."
    } else {
        Write-Warning "[finalize-modio-file] Platform status update failed; continuing to live update: $($_.Exception.Message)"
    }
}
if ($platformResponse -and ($platformResponse.PSObject.Properties.Name -contains "platforms")) {
    $platformSummary = @($platformResponse.platforms | ForEach-Object { "$($_.platform):$($_.status)" }) -join ","
    Write-Host "[finalize-modio-file] Platform status updated for file id=$($file.id): $platformSummary"
}

$editPayload = @{
    active = $true
}
if ($ExpectedVersion) {
    $editPayload.version = $ExpectedVersion
}
if ($Changelog) {
    $editPayload.changelog = $Changelog
}

$editUri = "{0}/games/{1}/mods/{2}/files/{3}" -f $ApiBase, $GameId, $ModId, $file.id
$updatedFile = Invoke-ModioRequest -Method "PUT" -Uri $editUri -Payload $editPayload
Write-Host "[finalize-modio-file] Live update requested for file id=$($updatedFile.id) filename=$($updatedFile.filename) version=$($updatedFile.version)"

$activeModfileId = Get-ActiveModfileId
$isLive = ($null -ne $activeModfileId) -and ([int64]$activeModfileId -eq [int64]$file.id)
if ($isLive) {
    Write-Host "[finalize-modio-file] Live status confirmed: active modfile id=$activeModfileId."
} else {
    $manualReason = if ($platformApprovalFailed) {
        "platform approval via the mod.io API was rejected (HTTP 403); the modfile must be enabled by hand."
    } else {
        "mod.io has not reported this file as the active modfile."
    }
    Write-Host "[finalize-modio-file] File id=$($file.id) is uploaded but NOT live: $manualReason"
    Send-ManualEnableRequest -File $file -ExpectedVersion $ExpectedVersion -Reason $manualReason
}
