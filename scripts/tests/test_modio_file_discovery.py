import shutil
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
PUBLISH_UI = ROOT / "scripts/publish-modio-ui.ps1"
FINALIZE = ROOT / "scripts/finalize-modio-file.ps1"


def _powershell(script: str) -> str:
    executable = shutil.which("pwsh") or shutil.which("powershell")
    if not executable:
        raise RuntimeError("PowerShell is required for mod.io discovery tests")
    result = subprocess.run(
        [executable, "-NoLogo", "-NoProfile", "-NonInteractive", "-Command", script],
        check=True,
        capture_output=True,
        text=True,
        timeout=20,
    )
    return result.stdout


def test_handoff_discovers_upload_beyond_default_first_100_files():
    script = rf'''
$ErrorActionPreference = "Stop"
$script:requestedUris = @()
$script:capturedLogs = New-Object System.Collections.Generic.List[string]
$script:token = "TEST_BEARER_SECRET_MUST_NOT_APPEAR_IN_LOGS"
$script:afterUnix = [int64][Math]::Floor(([DateTime]::UtcNow - [DateTime]::new(1970,1,1,0,0,0,[DateTimeKind]::Utc)).TotalSeconds) - 120
$script:oldest100 = @(1..100 | ForEach-Object {{ [pscustomobject]@{{ id=$_; date_added=($script:afterUnix - 2000 + ($_ * 10)); filename="old-$_.pak"; version="old" }} }})
$script:newest100 = @(103..4 | ForEach-Object {{ [pscustomobject]@{{ id=$_; date_added=($script:afterUnix - 2000 + ($_ * 20)); filename="file-$_.pak"; version="0.5.35.$_" }} }})
function Write-Diagnostic {{ param([string]$Message) $script:capturedLogs.Add($Message) }}
function Start-Sleep {{ param([int]$Seconds) }}
function Invoke-RestMethod {{
    param([string]$Method, [string]$Uri, [hashtable]$Headers, [int]$TimeoutSec)
    $script:requestedUris += $Uri
    if ($Uri -match '\?_sort=-date_added&_limit=100(?:&|$)') {{ $page = $script:newest100 }} else {{ $page = $script:oldest100 }}
    return [pscustomobject]@{{ data = @($page) }}
}}
$ast = [System.Management.Automation.Language.Parser]::ParseFile('{PUBLISH_UI}', [ref]$null, [ref]$null)
$functionAst = $ast.Find({{ param($node) $node -is [System.Management.Automation.Language.FunctionDefinitionAst] -and $node.Name -eq 'Wait-ForUploadHandoff' }}, $true)
if (-not $functionAst) {{ throw 'Wait-ForUploadHandoff not found in source AST' }}
$baselineFunction = $functionAst.Extent.Text.Replace('?_sort=-date_added&_limit=100', '')
Invoke-Expression $baselineFunction
$startedAt = [DateTime]::UtcNow
$baselineResult = Wait-ForUploadHandoff -ToolkitDirectory '' -StartedAt $startedAt -TimeoutSeconds 0 -ModioApiBase 'https://api.mod.io/v1' -ModioGameId 123 -ModioModId 456 -ModioAccessToken $script:token
if ($baselineResult) {{ throw 'baseline unexpectedly found the new file in the oldest 100 records' }}
$script:requestedUris = @()
Invoke-Expression $functionAst.Extent.Text
$currentResult = Wait-ForUploadHandoff -ToolkitDirectory '' -StartedAt $startedAt -TimeoutSeconds 0 -ModioApiBase 'https://api.mod.io/v1/' -ModioGameId 123 -ModioModId 456 -ModioAccessToken $script:token
if (-not $currentResult) {{ throw 'current function failed to find file 103 in the newest 100 records' }}
if ($script:requestedUris.Count -ne 1 -or $script:requestedUris[0] -notmatch '/games/123/mods/456/files\?_sort=-date_added&_limit=100$') {{ throw "unexpected handoff URI: $($script:requestedUris -join ',')" }}
if (($script:capturedLogs -join "`n") -match [regex]::Escape($script:token)) {{ throw 'handoff diagnostics exposed the bearer token' }}
Write-Output 'handoff baseline=miss current=found newest-file=103 auth-token-not-logged'
'''
    output = _powershell(script)
    assert "baseline=miss current=found newest-file=103" in output
    assert "auth-token-not-logged" in output


def test_finalizer_scans_latest_page_and_composes_platform_status_queries():
    script = rf'''
$ErrorActionPreference = "Stop"
$script:requestedUris = @()
$script:capturedLogs = New-Object System.Collections.Generic.List[string]
$script:token = "TEST_BEARER_SECRET_MUST_NOT_APPEAR_IN_LOGS"
$script:afterUnix = [int64][Math]::Floor(([DateTime]::UtcNow - [DateTime]::new(1970,1,1,0,0,0,[DateTimeKind]::Utc)).TotalSeconds) - 120
$script:oldest100 = @(1..100 | ForEach-Object {{ [pscustomobject]@{{ id=$_; date_added=($script:afterUnix - 2000 + ($_ * 10)); filename="old-$_.pak"; version="old" }} }})
$script:newest100 = @(103..4 | ForEach-Object {{ [pscustomobject]@{{ id=$_; date_added=($script:afterUnix - 2000 + ($_ * 20)); filename="file-$_.pak"; version="0.5.35.$_" }} }})
$script:ApiBase = 'https://api.mod.io/v1'
$script:GameId = 123
$script:ModId = 456
$script:AccessToken = $script:token
function Write-Host {{ param([Parameter(ValueFromRemainingArguments=$true)]$Object) $script:capturedLogs.Add(($Object -join ' ')) }}
function Invoke-ModioRequest {{
    param([string]$Method, [string]$Uri, [hashtable]$Payload)
    $script:requestedUris += $Uri
    if ($Uri -match '\?_sort=-date_added&_limit=100(?:&|$)') {{ $page = $script:newest100 }} else {{ $page = $script:oldest100 }}
    return [pscustomobject]@{{ data = @($page) }}
}}
$ast = [System.Management.Automation.Language.Parser]::ParseFile('{FINALIZE}', [ref]$null, [ref]$null)
$functionSources = @{{}}
foreach ($name in @('Get-ModioFiles', 'Find-NewestUploadedFile')) {{
    $functionAst = $ast.Find({{ param($node) $node -is [System.Management.Automation.Language.FunctionDefinitionAst] -and $node.Name -eq $name }}, $true)
    if (-not $functionAst) {{ throw "$name not found in source AST" }}
    $functionSources[$name] = $functionAst.Extent.Text
}}

# Recreate the previous unsorted API view from the actual functions, then prove
# it misses file 103 before executing the unchanged current-source functions.
$baselineGetFiles = $functionSources['Get-ModioFiles'].Replace('?_sort=-date_added&_limit=100', '').Replace('&platform_status=', '?platform_status=')
Invoke-Expression $baselineGetFiles
Invoke-Expression $functionSources['Find-NewestUploadedFile']
$baselineCandidate = Find-NewestUploadedFile -UploadedAfterUnix $script:afterUnix
if ($baselineCandidate) {{ throw "baseline unexpectedly found file $($baselineCandidate.id) in the oldest 100 records" }}
$script:requestedUris = @()
$script:capturedLogs.Clear()
Invoke-Expression $functionSources['Get-ModioFiles']
Invoke-Expression $functionSources['Find-NewestUploadedFile']
$candidate = Find-NewestUploadedFile -UploadedAfterUnix $script:afterUnix
if (-not $candidate -or [int]$candidate.id -ne 103) {{ throw "finalizer selected wrong file: $($candidate.id)" }}
if ($script:requestedUris.Count -ne 5) {{ throw "expected five file-view requests, got $($script:requestedUris.Count)" }}
foreach ($uri in $script:requestedUris) {{
    if ($uri -notmatch '\?_sort=-date_added&_limit=100') {{ throw "missing descending page parameters: $uri" }}
}}
if ($script:requestedUris[0] -match 'platform_status=') {{ throw "base view unexpectedly has platform_status: $($script:requestedUris[0])" }}
foreach ($status in @('pending_only', 'approved_only', 'live_and_pending', 'live_and_approved')) {{
    if (-not ($script:requestedUris | Where-Object {{ $_ -match "&platform_status=$status$" }})) {{ throw "bad query composition for platform_status=$status" }}
}}
if (($script:capturedLogs -join "`n") -match [regex]::Escape($script:token)) {{ throw 'finalizer diagnostics exposed the bearer token' }}
Write-Output 'finalizer baseline=miss current=found newest-file=103 platform-status-queries=4 auth-token-not-logged'
'''
    output = _powershell(script)
    assert "baseline=miss current=found newest-file=103" in output
    assert "platform-status-queries=4" in output
    assert "auth-token-not-logged" in output
