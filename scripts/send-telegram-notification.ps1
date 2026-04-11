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
$BotToken = Resolve-Setting -ExplicitValue $BotToken -EnvName "TG_BOT_TOKEN"
if ([string]::IsNullOrWhiteSpace($BotToken)) {
    $BotToken = Resolve-Setting -ExplicitValue $null -EnvName "BOT_TOKEN"
}
$ChatId = Resolve-Setting -ExplicitValue $ChatId -EnvName "TG_CHAT_ID"
$ThreadId = Resolve-Setting -ExplicitValue $ThreadId -EnvName "TG_THREAD_ID"

if ([string]::IsNullOrWhiteSpace($BotToken)) {
    throw "Telegram bot token is required. Pass -BotToken or set TG_BOT_TOKEN in the environment."
}

if ([string]::IsNullOrWhiteSpace($ChatId)) {
    throw "Telegram chat id is required. Pass -ChatId or set TG_CHAT_ID in the environment."
}

if ([string]::IsNullOrWhiteSpace($ThreadId)) {
    throw "Telegram thread id is required. Pass -ThreadId or set TG_THREAD_ID in the environment."
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
