param(
    [Parameter(Mandatory = $true)]
    [string]$Bg3ToolPath,

    [string]$ProjectName = "DnD 5.5e All-in-One BEYOND Russian Localization",
    [string]$ProjectPath = "",
    [int]$TimeoutSeconds = 900,
    [string]$DiagnosticPath = ""
)

$ErrorActionPreference = "Stop"

function Write-Diagnostic {
    param([string]$Message)

    $line = "[{0}] {1}" -f (Get-Date).ToString("o"), $Message
    Write-Host "[publish-modio-ui] $Message"
    if ($script:DiagnosticPath) {
        Add-Content -LiteralPath $script:DiagnosticPath -Value $line -Encoding utf8
    }
}

function Test-InteractiveDesktop {
    try {
        Add-Type -AssemblyName System.Windows.Forms
        return [System.Windows.Forms.SystemInformation]::UserInteractive
    } catch {
        return $false
    }
}

Add-Type -TypeDefinition @"
using System;
using System.Runtime.InteropServices;
public static class Bg3PublishWin32 {
    [DllImport("user32.dll")] public static extern bool SetForegroundWindow(IntPtr hWnd);
    [DllImport("user32.dll")] public static extern bool BringWindowToTop(IntPtr hWnd);
    [DllImport("user32.dll")] public static extern bool ShowWindow(IntPtr hWnd, int nCmdShow);
    [DllImport("user32.dll")] public static extern bool SetCursorPos(int X, int Y);
    [DllImport("user32.dll")] public static extern void mouse_event(uint dwFlags, uint dx, uint dy, uint dwData, UIntPtr dwExtraInfo);
    public const int SW_RESTORE = 9;
    public const int SW_MINIMIZE = 6;
    public const uint LEFTDOWN = 0x0002;
    public const uint LEFTUP = 0x0004;
}
"@

function Find-WindowByProcessId {
    param(
        [int]$ProcessId,
        [int]$TimeoutSeconds
    )

    $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
    do {
        $process = Get-Process -Id $ProcessId -ErrorAction SilentlyContinue
        if (-not $process) {
            throw "Toolkit process $ProcessId exited before its main window was available."
        }

        $condition = New-Object System.Windows.Automation.PropertyCondition(
            [System.Windows.Automation.AutomationElement]::ProcessIdProperty,
            $ProcessId
        )
        $window = $null
        try {
            $window = [System.Windows.Automation.AutomationElement]::RootElement.FindFirst(
                [System.Windows.Automation.TreeScope]::Children,
                $condition
            )
        } catch [System.Windows.Automation.ElementNotAvailableException] {
            Start-Sleep -Seconds 2
            continue
        }
        if ($window) {
            return $window
        }
        Start-Sleep -Seconds 2
    } while ((Get-Date) -lt $deadline)

    return $null
}

function Set-ToolkitForeground {
    param([int]$ProcessId)

    $process = Get-Process -Id $ProcessId -ErrorAction SilentlyContinue
    if ($process -and $process.MainWindowHandle -ne 0) {
        [Bg3PublishWin32]::ShowWindow($process.MainWindowHandle, [Bg3PublishWin32]::SW_RESTORE) | Out-Null
        [Bg3PublishWin32]::BringWindowToTop($process.MainWindowHandle) | Out-Null
        [Bg3PublishWin32]::SetForegroundWindow($process.MainWindowHandle) | Out-Null
        try {
            (New-Object -ComObject WScript.Shell).AppActivate($ProcessId) | Out-Null
        } catch {
            Write-Diagnostic "WScript AppActivate failed: $($_.Exception.Message)"
        }
        Start-Sleep -Milliseconds 500
    }
}

function Minimize-OtherWindows {
    param([int]$KeepProcessId)

    Get-Process -ErrorAction SilentlyContinue |
        Where-Object { $_.Id -ne $KeepProcessId -and $_.MainWindowHandle -ne 0 } |
        ForEach-Object {
            try {
                Write-Diagnostic "Minimizing window owned by process '$($_.ProcessName)' ($($_.Id))."
                [Bg3PublishWin32]::ShowWindow($_.MainWindowHandle, [Bg3PublishWin32]::SW_MINIMIZE) | Out-Null
            } catch {
                Write-Diagnostic "Failed to minimize '$($_.ProcessName)' ($($_.Id)): $($_.Exception.Message)"
            }
        }
}

function Invoke-MouseClick {
    param(
        [int]$X,
        [int]$Y
    )

    [Bg3PublishWin32]::SetCursorPos($X, $Y) | Out-Null
    Start-Sleep -Milliseconds 150
    [Bg3PublishWin32]::mouse_event([Bg3PublishWin32]::LEFTDOWN, 0, 0, 0, [UIntPtr]::Zero)
    Start-Sleep -Milliseconds 80
    [Bg3PublishWin32]::mouse_event([Bg3PublishWin32]::LEFTUP, 0, 0, 0, [UIntPtr]::Zero)
    Start-Sleep -Milliseconds 500
}

function Invoke-WindowRelativeClick {
    param(
        [System.Windows.Automation.AutomationElement]$Window,
        [int]$X,
        [int]$Y,
        [string]$Label
    )

    $rect = $Window.Current.BoundingRectangle
    if ($rect.IsEmpty) {
        throw "Cannot click '$Label' because Toolkit window bounds are unavailable."
    }

    Write-Diagnostic "Clicking '$Label' at window-relative coordinates $X,$Y."
    Invoke-MouseClick -X ([int]($rect.Left + $X)) -Y ([int]($rect.Top + $Y))
}

function Send-TextToForeground {
    param([string]$Text)

    Add-Type -AssemblyName System.Windows.Forms
    [System.Windows.Forms.SendKeys]::SendWait($Text)
}

function Send-KeyToForeground {
    param([string]$Key)

    Add-Type -AssemblyName System.Windows.Forms
    [System.Windows.Forms.SendKeys]::SendWait($Key)
}

function Select-ToolkitProjectFromBrowser {
    param(
        [System.Windows.Automation.AutomationElement]$Window,
        [int]$ProcessId,
        [string]$ProjectName,
        [string]$ProjectPath
    )

    Write-Diagnostic "Selecting Toolkit project from browser by fallback coordinates."
    Minimize-OtherWindows -KeepProcessId $ProcessId
    Set-ToolkitForeground -ProcessId $ProcessId

    $screen = [System.Windows.Forms.Screen]::PrimaryScreen.Bounds
    Write-Diagnostic "Using screen fallback $($screen.Width)x$($screen.Height)."
    $searchX = [int]($screen.Width * 0.64)
    $searchY = 170
    $cardX = [int]($screen.Width * 0.50)
    $cardY = 312
    $selectX = [int]($screen.Width - 420)
    $selectY = [int]($screen.Height - 175)

    Write-Diagnostic "Clicking 'Project browser search' at absolute coordinates $searchX,$searchY."
    Invoke-MouseClick -X $searchX -Y $searchY
    Start-Sleep -Milliseconds 300
    Send-KeyToForeground -Key "^(a)"
    Start-Sleep -Milliseconds 100

    $searchText = if ($ProjectPath) { $ProjectPath } else { $ProjectName }
    Send-TextToForeground -Text $searchText
    Start-Sleep -Seconds 3

    Write-Diagnostic "Clicking 'Project card' at absolute coordinates $cardX,$cardY."
    Invoke-MouseClick -X $cardX -Y $cardY
    Start-Sleep -Milliseconds 500
    Write-Diagnostic "Clicking 'Select project button' at absolute coordinates $selectX,$selectY."
    Invoke-MouseClick -X $selectX -Y $selectY
    Start-Sleep -Seconds 20
}

function Find-DescendantByName {
    param(
        [System.Windows.Automation.AutomationElement]$Root,
        [string[]]$Names
    )

    foreach ($name in $Names) {
        $condition = New-Object System.Windows.Automation.PropertyCondition(
            [System.Windows.Automation.AutomationElement]::NameProperty,
            $name
        )
        $element = $null
        try {
            $element = $Root.FindFirst([System.Windows.Automation.TreeScope]::Descendants, $condition)
        } catch [System.Windows.Automation.ElementNotAvailableException] {
            return $null
        }
        if ($element) {
            return $element
        }
    }

    return $null
}

function Find-DescendantsByName {
    param(
        [System.Windows.Automation.AutomationElement]$Root,
        [string[]]$Names
    )

    $results = @()
    foreach ($name in $Names) {
        $condition = New-Object System.Windows.Automation.PropertyCondition(
            [System.Windows.Automation.AutomationElement]::NameProperty,
            $name
        )
        try {
            $found = $Root.FindAll([System.Windows.Automation.TreeScope]::Descendants, $condition)
            foreach ($element in $found) {
                $results += $element
            }
        } catch [System.Windows.Automation.ElementNotAvailableException] {
            continue
        }
    }

    return @($results)
}

function Find-ButtonByName {
    param(
        [System.Windows.Automation.AutomationElement]$Root,
        [string[]]$Names
    )

    $buttons = Find-DescendantsByName -Root $Root -Names $Names
    foreach ($button in $buttons) {
        try {
            if ($button.Current.ControlType -eq [System.Windows.Automation.ControlType]::Button) {
                return $button
            }
        } catch [System.Windows.Automation.ElementNotAvailableException] {
            continue
        }
    }

    return $buttons | Select-Object -First 1
}

function Find-DescendantByAutomationId {
    param(
        [System.Windows.Automation.AutomationElement]$Root,
        [string]$AutomationId
    )

    $condition = New-Object System.Windows.Automation.PropertyCondition(
        [System.Windows.Automation.AutomationElement]::AutomationIdProperty,
        $AutomationId
    )
    try {
        return $Root.FindFirst([System.Windows.Automation.TreeScope]::Descendants, $condition)
    } catch [System.Windows.Automation.ElementNotAvailableException] {
        return $null
    }
}

function Set-ElementValue {
    param(
        [System.Windows.Automation.AutomationElement]$Element,
        [string]$Value,
        [string]$Label
    )

    if (-not $Element) {
        throw "UI element '$Label' was not found."
    }

    $valuePattern = $null
    if ($Element.TryGetCurrentPattern([System.Windows.Automation.ValuePattern]::Pattern, [ref]$valuePattern)) {
        Write-Diagnostic "Setting '$Label'."
        $valuePattern.SetValue($Value)
        return
    }

    throw "UI element '$Label' does not expose ValuePattern."
}

function Invoke-Element {
    param(
        [System.Windows.Automation.AutomationElement]$Element,
        [string]$Label
    )

    if (-not $Element) {
        throw "UI element '$Label' was not found."
    }

    $invokePattern = $null
    if ($Element.TryGetCurrentPattern([System.Windows.Automation.InvokePattern]::Pattern, [ref]$invokePattern)) {
        Write-Diagnostic "Invoking '$Label'."
        $invokePattern.Invoke()
        return
    }

    $selectionPattern = $null
    if ($Element.TryGetCurrentPattern([System.Windows.Automation.SelectionItemPattern]::Pattern, [ref]$selectionPattern)) {
        Write-Diagnostic "Selecting '$Label'."
        $selectionPattern.Select()
        return
    }

    throw "UI element '$Label' does not expose InvokePattern or SelectionItemPattern."
}

function Open-ProjectSettings {
    param(
        [System.Windows.Automation.AutomationElement]$Window,
        [int]$ProcessId
    )

    Minimize-OtherWindows -KeepProcessId $ProcessId
    Set-ToolkitForeground -ProcessId $ProcessId

    $projectMenu = Find-DescendantByName -Root $Window -Names @("Project", "_Project")
    if ($projectMenu) {
        Invoke-Element -Element $projectMenu -Label "Project"
        Start-Sleep -Seconds 1
    } else {
        Invoke-WindowRelativeClick -Window $Window -X 255 -Y 40 -Label "Project menu"
    }

    $projectSettings = Find-DescendantByName -Root ([System.Windows.Automation.AutomationElement]::RootElement) -Names @(
        "Project Settings...",
        "Project Settings",
        "Project settings",
        "Settings"
    )
    if ($projectSettings) {
        Invoke-Element -Element $projectSettings -Label "Project Settings"
    } else {
        Invoke-WindowRelativeClick -Window $Window -X 320 -Y 64 -Label "Project Settings menu item"
    }

    Start-Sleep -Seconds 5
}

function Invoke-OptionalButton {
    param(
        [string[]]$Names,
        [string]$Label
    )

    $button = Find-ButtonByName -Root ([System.Windows.Automation.AutomationElement]::RootElement) -Names $Names
    if (-not $button) {
        Write-Diagnostic "Optional button '$Label' was not found."
        return $false
    }

    Invoke-Element -Element $button -Label $Label
    return $true
}

function Wait-ForLogSuccess {
    param(
        [string]$ToolkitDirectory,
        [datetime]$StartedAt,
        [int]$TimeoutSeconds
    )

    $successPatterns = @(
        'publish.*success',
        'uploaded.*mod',
        'mod\.io.*success',
        'file manager',
        'published'
    )

    $failurePatterns = @(
        'publish.*fail',
        'upload.*fail',
        'authentication.*fail',
        'unauthorized',
        'error'
    )

    $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
    do {
        $logs = Get-ChildItem -LiteralPath $ToolkitDirectory -File -ErrorAction SilentlyContinue |
            Where-Object { $_.LastWriteTime -ge $StartedAt -and $_.Name -match '(log|error|network)' } |
            Sort-Object LastWriteTime -Descending |
            Select-Object -First 20

        foreach ($log in $logs) {
            $text = Get-Content -LiteralPath $log.FullName -Raw -ErrorAction SilentlyContinue
            if (-not $text) {
                continue
            }

            foreach ($failurePattern in $failurePatterns) {
                if ($text -match $failurePattern) {
                    Write-Diagnostic "Potential failure signal in $($log.Name): $failurePattern"
                }
            }

            foreach ($successPattern in $successPatterns) {
                if ($text -match $successPattern) {
                    Write-Diagnostic "Success signal in $($log.Name): $successPattern"
                    return $true
                }
            }
        }

        Start-Sleep -Seconds 5
    } while ((Get-Date) -lt $deadline)

    return $false
}

function Wait-ForUploadHandoff {
    param(
        [string]$ToolkitDirectory,
        [datetime]$StartedAt,
        [int]$TimeoutSeconds
    )

    $logPatterns = @(
        'mod\.io',
        'file manager',
        'uploaded.*mod',
        'publish.*success'
    )

    $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
    do {
        $browserWindow = Get-Process -ErrorAction SilentlyContinue |
            Where-Object { $_.MainWindowTitle -match 'mod\.io|File manager|File Manager|Edit .*mod' } |
            Select-Object -First 1
        if ($browserWindow) {
            Write-Diagnostic "Detected mod.io browser handoff: $($browserWindow.MainWindowTitle)"
            return $true
        }

        $logs = Get-ChildItem -LiteralPath $ToolkitDirectory -File -ErrorAction SilentlyContinue |
            Where-Object { $_.LastWriteTime -ge $StartedAt -and $_.Name -match '(log|error|network)' } |
            Sort-Object LastWriteTime -Descending |
            Select-Object -First 20

        foreach ($log in $logs) {
            $text = Get-Content -LiteralPath $log.FullName -Raw -ErrorAction SilentlyContinue
            if (-not $text) {
                continue
            }

            foreach ($pattern in $logPatterns) {
                if ($text -match $pattern) {
                    Write-Diagnostic "Detected Toolkit upload handoff in $($log.Name): $pattern"
                    return $true
                }
            }
        }

        Start-Sleep -Seconds 5
    } while ((Get-Date) -lt $deadline)

    return $false
}

$resolvedBg3ToolPath = [System.IO.Path]::GetFullPath($Bg3ToolPath)
if (-not (Test-Path -LiteralPath $resolvedBg3ToolPath)) {
    throw "BG3 Toolkit executable was not found: '$resolvedBg3ToolPath'."
}

if (-not $DiagnosticPath) {
    $diagnosticRoot = if ($env:RUNNER_TEMP) { $env:RUNNER_TEMP } else { $env:TEMP }
    $DiagnosticPath = Join-Path $diagnosticRoot "modio-publish-ui.log"
}
$script:DiagnosticPath = $DiagnosticPath
New-Item -ItemType Directory -Path (Split-Path -Parent $script:DiagnosticPath) -Force | Out-Null
Set-Content -LiteralPath $script:DiagnosticPath -Value "" -Encoding utf8

if (-not (Test-InteractiveDesktop)) {
    throw "BG3 Toolkit GUI publishing requires an interactive Windows desktop. Run the self-hosted runner in an interactive user session."
}

Add-Type -AssemblyName UIAutomationClient
Add-Type -AssemblyName UIAutomationTypes

$toolkitDirectory = Split-Path -Parent $resolvedBg3ToolPath
$startedAt = Get-Date
$arguments = @()

Write-Diagnostic "Starting Toolkit: $resolvedBg3ToolPath $($arguments -join ' ')"
if ($arguments.Count -gt 0) {
    $process = Start-Process -FilePath $resolvedBg3ToolPath -ArgumentList $arguments -WorkingDirectory $toolkitDirectory -PassThru -WindowStyle Normal
} else {
    $process = Start-Process -FilePath $resolvedBg3ToolPath -WorkingDirectory $toolkitDirectory -PassThru -WindowStyle Normal
}

try {
    $window = Find-WindowByProcessId -ProcessId $process.Id -TimeoutSeconds 120
    if (-not $window) {
        throw "Toolkit main window was not found."
    }

    Start-Sleep -Seconds 10

    if ($ProjectPath) {
        $projectPathInput = Find-DescendantByAutomationId -Root $window -AutomationId "m_LoadPath"
        if ($projectPathInput) {
            Set-ElementValue -Element $projectPathInput -Value $ProjectPath -Label "Project path"
            Start-Sleep -Seconds 2

            $selectProject = Find-DescendantByAutomationId -Root $window -AutomationId "m_OpenButton"
            Invoke-Element -Element $selectProject -Label "Select project"
            Start-Sleep -Seconds 20

            $window = Find-WindowByProcessId -ProcessId $process.Id -TimeoutSeconds 60
            if (-not $window) {
                throw "Toolkit main window was not found after project selection."
            }

            Invoke-OptionalButton -Names @("Cancel", "Отмена") -Label "Level selector cancel" | Out-Null
        } else {
            Write-Diagnostic "Project path field was not visible; using browser coordinate fallback."
            Select-ToolkitProjectFromBrowser -Window $window -ProcessId $process.Id -ProjectName $ProjectName -ProjectPath $ProjectPath
            $window = Find-WindowByProcessId -ProcessId $process.Id -TimeoutSeconds 60
            if (-not $window) {
                throw "Toolkit main window was not found after coordinate project selection."
            }
            Invoke-OptionalButton -Names @("Cancel", "Отмена") -Label "Level selector cancel" | Out-Null
        }
    }

    Open-ProjectSettings -Window $window -ProcessId $process.Id

    if (Invoke-OptionalButton -Names @("Save", "Сохранить") -Label "Project settings save") {
        Start-Sleep -Seconds 5
        $window = Find-WindowByProcessId -ProcessId $process.Id -TimeoutSeconds 60
        if (-not $window) {
            throw "Toolkit main window was not found after saving project settings."
        }
        Open-ProjectSettings -Window $window -ProcessId $process.Id
    }

    $publishLocal = Find-ButtonByName -Root ([System.Windows.Automation.AutomationElement]::RootElement) -Names @(
        "Publish Local",
        "Publish locally",
        "Опубликовать локально"
    )
    Invoke-Element -Element $publishLocal -Label "Publish Local"
    if (-not (Wait-ForLogSuccess -ToolkitDirectory $toolkitDirectory -StartedAt $startedAt -TimeoutSeconds ([Math]::Min($TimeoutSeconds, 180)))) {
        throw "Toolkit did not report a successful local publish. Diagnostic log: $script:DiagnosticPath"
    }

    Set-ToolkitForeground -ProcessId $process.Id
    Start-Sleep -Seconds 5

    $publish = Find-ButtonByName -Root ([System.Windows.Automation.AutomationElement]::RootElement) -Names @(
        "Publish",
        "Publish to Mod.io",
        "Publish to mod.io",
        "Опубликовать"
    )
    Invoke-Element -Element $publish -Label "Publish"

    if (-not (Wait-ForUploadHandoff -ToolkitDirectory $toolkitDirectory -StartedAt $startedAt -TimeoutSeconds $TimeoutSeconds)) {
        throw "Toolkit did not hand off a new upload to mod.io within $TimeoutSeconds seconds. Diagnostic log: $script:DiagnosticPath"
    }

    Write-Diagnostic "Toolkit upload handoff completed; API finalization should verify scan and live status."
} finally {
    if ($process -and -not $process.HasExited) {
        try {
            $process.CloseMainWindow() | Out-Null
            if (-not $process.WaitForExit(30000)) {
                $process.Kill()
            }
        } catch {
            Write-Diagnostic "Failed to close Toolkit process cleanly: $($_.Exception.Message)"
        }
    }
}
