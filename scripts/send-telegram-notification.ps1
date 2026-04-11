[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [string]$BotToken,

    [Parameter(Mandatory = $true)]
    [string]$ChatId,

    [Parameter(Mandatory = $true)]
    [string]$ThreadId,

    [Parameter(Mandatory = $true)]
    [string]$Text,

    [switch]$DisableNotification
)

$ErrorActionPreference = "Stop"

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
