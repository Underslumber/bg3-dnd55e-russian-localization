[CmdletBinding()]
param(
    [Parameter()]
    [string]$BotToken,

    [Parameter()]
    [string]$ChatId,

    [Parameter()]
    [string]$ThreadId,

    [Parameter(Mandatory = $true)]
    [string]$Text,

    [switch]$DisableNotification
)

$ErrorActionPreference = "Stop"

function Import-DotEnvFile {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Path
    )

    if (-not (Test-Path -LiteralPath $Path)) {
        return
    }

    foreach ($line in [System.IO.File]::ReadAllLines($Path)) {
        $trimmedLine = $line.Trim()
        if (-not $trimmedLine -or $trimmedLine.StartsWith("#")) {
            continue
        }

        $separatorIndex = $trimmedLine.IndexOf("=")
        if ($separatorIndex -lt 1) {
            continue
        }

        $name = $trimmedLine.Substring(0, $separatorIndex).Trim()
        $value = $trimmedLine.Substring($separatorIndex + 1).Trim()

        if (
            ($value.StartsWith('"') -and $value.EndsWith('"')) -or
            ($value.StartsWith("'") -and $value.EndsWith("'"))
        ) {
            $value = $value.Substring(1, $value.Length - 2)
        }

        [System.Environment]::SetEnvironmentVariable($name, $value, "Process")
    }
}

function Resolve-Setting {
    param(
        [string]$ExplicitValue,
        [Parameter(Mandatory = $true)]
        [string]$EnvName
    )

    if (-not [string]::IsNullOrWhiteSpace($ExplicitValue)) {
        return $ExplicitValue
    }

    $envValue = [System.Environment]::GetEnvironmentVariable($EnvName, "Process")
    if (-not [string]::IsNullOrWhiteSpace($envValue)) {
        return $envValue
    }

    return $null
}

$repoRoot = [System.IO.Path]::GetFullPath((Join-Path $PSScriptRoot ".."))
$localEnvPath = Join-Path $repoRoot ".env.local"
Import-DotEnvFile -Path $localEnvPath

$BotToken = Resolve-Setting -ExplicitValue $BotToken -EnvName "BOT_TOKEN"
$ChatId = Resolve-Setting -ExplicitValue $ChatId -EnvName "TG_CHAT_ID"
$ThreadId = Resolve-Setting -ExplicitValue $ThreadId -EnvName "TG_THREAD_ID"

if ([string]::IsNullOrWhiteSpace($BotToken)) {
    throw "Telegram bot token is required. Pass -BotToken or set BOT_TOKEN in .env.local."
}

if ([string]::IsNullOrWhiteSpace($ChatId)) {
    throw "Telegram chat id is required. Pass -ChatId or set TG_CHAT_ID in .env.local."
}

if ([string]::IsNullOrWhiteSpace($ThreadId)) {
    throw "Telegram thread id is required. Pass -ThreadId or set TG_THREAD_ID in .env.local."
}

$normalizedText = $Text.
    Replace("``r``n", "`r`n").
    Replace("``n", "`n").
    Replace("%0A", "`n")

$body = @{
    chat_id = $ChatId
    message_thread_id = $ThreadId
    parse_mode = "HTML"
    text = $normalizedText
}

if ($DisableNotification) {
    $body.disable_notification = "true"
}

Invoke-RestMethod `
    -Method Post `
    -Uri ("https://api.telegram.org/bot{0}/sendMessage" -f $BotToken) `
    -Body $body | Out-Null
