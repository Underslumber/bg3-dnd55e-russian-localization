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
    public delegate bool EnumWindowsProc(IntPtr hWnd, IntPtr lParam);
    [StructLayout(LayoutKind.Sequential)]
    public struct RECT {
        public int Left;
        public int Top;
        public int Right;
        public int Bottom;
    }
    [DllImport("user32.dll")] public static extern bool EnumWindows(EnumWindowsProc lpEnumFunc, IntPtr lParam);
    [DllImport("user32.dll")] public static extern uint GetWindowThreadProcessId(IntPtr hWnd, out int lpdwProcessId);
    [DllImport("user32.dll")] public static extern int GetWindowText(IntPtr hWnd, System.Text.StringBuilder lpString, int nMaxCount);
    [DllImport("user32.dll")] public static extern bool IsWindowVisible(IntPtr hWnd);
    [DllImport("user32.dll")] public static extern bool GetWindowRect(IntPtr hWnd, out RECT lpRect);
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

        $allSnapshots = @(Get-VisibleWindowSnapshot -ProcessId $ProcessId)

        # Detect and dismiss small error/blocker dialogs (e.g. "Can't run 2 editor instances")
        # before they prevent the main window from appearing.
        $errorDialogs = $allSnapshots | Where-Object { $_.Title -in @("Error", "Warning", "Glasses") -and $_.Height -lt 200 }
        foreach ($dlg in $errorDialogs) {
            Write-Diagnostic "Dismissing blocker dialog pid=$ProcessId title='$($dlg.Title)' rect=$($dlg.Left),$($dlg.Top),$($dlg.Right),$($dlg.Bottom)."
            [Bg3PublishWin32]::PostMessage($dlg.Handle, 0x0010, [IntPtr]::Zero, [IntPtr]::Zero) | Out-Null
        }

        $windowSnapshot = $allSnapshots |
            Where-Object { $_.Width -gt 300 -and $_.Height -gt 200 } |
            Sort-Object @{ Expression = { if ($_.Title -like "Glasses*") { 0 } else { 1 } } }, Width -Descending |
            Select-Object -First 1
        if ($windowSnapshot) {
            return [System.Windows.Automation.AutomationElement]::FromHandle($windowSnapshot.Handle)
        }

        Start-Sleep -Seconds 2
    } while ((Get-Date) -lt $deadline)

    return $null
}

function Get-ToolkitProcess {
    param([string]$Path)

    return Get-ToolkitProcesses -Path $Path | Select-Object -First 1
}

function Get-ToolkitProcesses {
    param([string]$Path)

    $fullPath = [System.IO.Path]::GetFullPath($Path)
    return @(Get-Process -Name "Glasses" -ErrorAction SilentlyContinue |
        Where-Object { $_.Path -and ([System.IO.Path]::GetFullPath($_.Path) -eq $fullPath) } |
        Sort-Object StartTime -Descending)
}

function Find-ToolkitWindow {
    param(
        [string]$Path,
        [int]$TimeoutSeconds,
        [string]$ProjectName = ""
    )

    $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
    do {
        $toolkitProcesses = Get-ToolkitProcesses -Path $Path
        foreach ($toolkitProcess in $toolkitProcesses) {
            try {
                if ($ProjectName) {
                    $projectWindow = Get-VisibleWindowSnapshot -ProcessId $toolkitProcess.Id |
                        Where-Object { $_.Title -like "Glasses*" -and $_.Title.Contains($ProjectName) } |
                        Select-Object -First 1
                    if ($projectWindow) {
                        $window = [System.Windows.Automation.AutomationElement]::FromHandle($projectWindow.Handle)
                        return @{ Process = $toolkitProcess; Window = $window }
                    }
                    continue
                }

                $window = Find-WindowByProcessId -ProcessId $toolkitProcess.Id -TimeoutSeconds 5
                if ($window) {
                    return @{ Process = $toolkitProcess; Window = $window }
                }
            } catch {
                Write-Diagnostic "Toolkit process lookup skipped: $($_.Exception.Message)"
            }
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

function Get-VisibleWindowSnapshot {
    param([int]$ProcessId)

    $windows = New-Object System.Collections.Generic.List[object]
    $callback = [Bg3PublishWin32+EnumWindowsProc]{
        param([IntPtr]$Handle, [IntPtr]$Param)

        [int]$windowProcessId = 0
        [Bg3PublishWin32]::GetWindowThreadProcessId($Handle, [ref]$windowProcessId) | Out-Null
        if ([int]$windowProcessId -eq $ProcessId -and [Bg3PublishWin32]::IsWindowVisible($Handle)) {
            $titleBuilder = New-Object System.Text.StringBuilder 512
            [Bg3PublishWin32]::GetWindowText($Handle, $titleBuilder, $titleBuilder.Capacity) | Out-Null
            $rect = New-Object Bg3PublishWin32+RECT
            [Bg3PublishWin32]::GetWindowRect($Handle, [ref]$rect) | Out-Null
            $windows.Add([pscustomobject]@{
                Handle = $Handle
                Title = $titleBuilder.ToString()
                Left = $rect.Left
                Top = $rect.Top
                Right = $rect.Right
                Bottom = $rect.Bottom
                Width = $rect.Right - $rect.Left
                Height = $rect.Bottom - $rect.Top
            }) | Out-Null
        }

        return $true
    }

    [Bg3PublishWin32]::EnumWindows($callback, [IntPtr]::Zero) | Out-Null
    return @($windows.ToArray())
}

function Find-BrowserWindow {
    param([int]$ProcessId)

    return Get-VisibleWindowSnapshot -ProcessId $ProcessId |
        Where-Object { $_.Title -eq "Browser" -and $_.Width -gt 500 -and $_.Height -gt 300 } |
        Sort-Object Width -Descending |
        Select-Object -First 1
}

function Wait-ForBrowserContent {
    param(
        [pscustomobject]$Browser,
        [int]$TimeoutSeconds = 90,
        [int]$MinDescendantCount = 15
    )

    Write-Diagnostic "Waiting for browser project list to load (timeout=${TimeoutSeconds}s, threshold=$MinDescendantCount descendants)..."
    $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
    $lastBucket = -1
    do {
        try {
            $elem = [System.Windows.Automation.AutomationElement]::FromHandle($Browser.Handle)
            $all = $elem.FindAll(
                [System.Windows.Automation.TreeScope]::Descendants,
                [System.Windows.Automation.Condition]::TrueCondition
            )
            $count = $all.Count
            $bucket = if ($count -lt 5) { 0 } elseif ($count -lt $MinDescendantCount) { 1 } else { 2 }
            if ($bucket -ne $lastBucket) {
                Write-Diagnostic "Browser UIA descendants: $count."
                $lastBucket = $bucket
            }
            if ($count -ge $MinDescendantCount) {
                Write-Diagnostic "Browser content ready ($count descendants)."
                return $true
            }
        } catch {
            Write-Diagnostic "Browser UIA check error: $($_.Exception.Message)"
        }
        Start-Sleep -Milliseconds 750
    } while ((Get-Date) -lt $deadline)

    Write-Diagnostic "Browser content wait timed out after ${TimeoutSeconds}s; proceeding anyway."
    return $false
}

function Wait-ForPublishButtonEnabled {
    param(
        [Parameter(Mandatory)] [int]$ButtonX,
        [Parameter(Mandatory)] [int]$ButtonY,
        [int]$TimeoutSeconds = 60,
        [int]$PollIntervalMs = 500
    )

    Write-Diagnostic "Waiting for Publish button to become enabled at ($ButtonX,$ButtonY) (timeout=${TimeoutSeconds}s)..."
    $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
    $lastState = $null
    do {
        try {
            $point = New-Object System.Windows.Point($ButtonX, $ButtonY)
            $elem = [System.Windows.Automation.AutomationElement]::FromPoint($point)
            if ($elem) {
                $isEnabled = $elem.GetCurrentPropertyValue(
                    [System.Windows.Automation.AutomationElement]::IsEnabledProperty)
                if ($isEnabled -ne $lastState) {
                    Write-Diagnostic "Publish button IsEnabled=$isEnabled at ($ButtonX,$ButtonY)."
                    $lastState = $isEnabled
                }
                if ($isEnabled) { return $true }
            }
        } catch {
            Write-Diagnostic "FromPoint check failed: $($_.Exception.Message)"
        }
        Start-Sleep -Milliseconds $PollIntervalMs
    } while ((Get-Date) -lt $deadline)

    return $false
}

function Dismiss-LevelSelector {
    param(
        [int]$ProcessId,
        [int]$TimeoutSeconds = 60
    )

    $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
    $browserSeen = $false
    $missingSince = $null
    do {
        $browser = Find-BrowserWindow -ProcessId $ProcessId
        if (-not $browser) {
            if ($browserSeen) {
                Write-Diagnostic "Level selector browser is not visible."
                return $true
            }

            if (-not $missingSince) {
                $missingSince = Get-Date
            }
            if (((Get-Date) - $missingSince).TotalSeconds -ge 30) {
                Write-Diagnostic "Level selector browser did not appear during settle wait."
                return $true
            }

            Start-Sleep -Seconds 1
            continue
        }

        $browserSeen = $true
        Write-Diagnostic "Closing level selector browser at $($browser.Left),$($browser.Top),$($browser.Right),$($browser.Bottom)."
        [Bg3PublishWin32]::ShowWindow($browser.Handle, [Bg3PublishWin32]::SW_RESTORE) | Out-Null
        [Bg3PublishWin32]::BringWindowToTop($browser.Handle) | Out-Null
        [Bg3PublishWin32]::SetForegroundWindow($browser.Handle) | Out-Null
        Start-Sleep -Milliseconds 500

        Send-KeyToForeground -Key "{ESC}"
        Start-Sleep -Seconds 2

        $browser = Find-BrowserWindow -ProcessId $ProcessId
        if (-not $browser) {
            Write-Diagnostic "Level selector closed after Escape."
            return $true
        }

        $cancelX = [Math]::Max($browser.Left + 100, $browser.Right - 170)
        $cancelY = [Math]::Max($browser.Top + 100, $browser.Bottom - 35)
        Write-Diagnostic "Clicking level selector Cancel at absolute coordinates $cancelX,$cancelY."
        Invoke-MouseClick -X ([int]$cancelX) -Y ([int]$cancelY)
        Start-Sleep -Seconds 3
    } while ((Get-Date) -lt $deadline)

    return -not (Find-BrowserWindow -ProcessId $ProcessId)
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

function Invoke-ToolkitRelativeClick {
    param(
        [int]$ProcessId,
        [int]$X,
        [int]$Y,
        [string]$Label
    )

    $mainWindow = Get-VisibleWindowSnapshot -ProcessId $ProcessId |
        Where-Object { $_.Title -like "Glasses*" -and $_.Width -gt 600 -and $_.Height -gt 400 } |
        Sort-Object Width -Descending |
        Select-Object -First 1
    if (-not $mainWindow) {
        throw "Cannot click '$Label' because Toolkit main window bounds are unavailable."
    }

    $absoluteX = [int]($mainWindow.Left + $X)
    $absoluteY = [int]($mainWindow.Top + $Y)
    Write-Diagnostic "Clicking '$Label' at Toolkit-relative coordinates $X,$Y."
    Invoke-MouseClick -X $absoluteX -Y $absoluteY
}

function Find-ProjectSettingsWindow {
    param(
        [int]$ProcessId,
        [int]$TimeoutSeconds = 30
    )

    $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
    do {
        $settingsWindow = Get-VisibleWindowSnapshot -ProcessId $ProcessId |
            Where-Object { $_.Title -eq "Project Settings" -and $_.Width -gt 500 -and $_.Height -gt 400 } |
            Sort-Object Width -Descending |
            Select-Object -First 1
        if ($settingsWindow) {
            return $settingsWindow
        }

        Start-Sleep -Seconds 1
    } while ((Get-Date) -lt $deadline)

    return $null
}

function Invoke-ProjectSettingsRelativeClick {
    param(
        [int]$ProcessId,
        [int]$X,
        [int]$Y,
        [string]$Label
    )

    $settingsWindow = Find-ProjectSettingsWindow -ProcessId $ProcessId -TimeoutSeconds 10
    if (-not $settingsWindow) {
        throw "Cannot click '$Label' because Project Settings window bounds are unavailable."
    }

    [Bg3PublishWin32]::ShowWindow($settingsWindow.Handle, [Bg3PublishWin32]::SW_RESTORE) | Out-Null
    [Bg3PublishWin32]::BringWindowToTop($settingsWindow.Handle) | Out-Null
    [Bg3PublishWin32]::SetForegroundWindow($settingsWindow.Handle) | Out-Null
    Start-Sleep -Milliseconds 300

    $absoluteX = [int]($settingsWindow.Left + $X)
    $absoluteY = [int]($settingsWindow.Top + $Y)
    Write-Diagnostic "Clicking '$Label' at Project Settings-relative coordinates $X,$Y."
    Invoke-MouseClick -X $absoluteX -Y $absoluteY
}

function Get-ProjectSettingsFooterButtonCoords {
    param(
        [int]$ProcessId,
        [ValidateSet("Save", "Cancel", "PublishLocal", "Publish")]
        [string]$Button
    )

    $settingsWindow = Find-ProjectSettingsWindow -ProcessId $ProcessId -TimeoutSeconds 10
    if (-not $settingsWindow) {
        throw "Project Settings window was not found for '$Button' coord lookup."
    }

    $relY = [int]($settingsWindow.Bottom - $settingsWindow.Top - 24)
    switch ($Button) {
        "Save"         { $relX = [int]($settingsWindow.Right - $settingsWindow.Left - 57) }
        "Cancel"       { $relX = [int]($settingsWindow.Right - $settingsWindow.Left - 162) }
        "PublishLocal" { $relX = 57 }
        "Publish"      { $relX = 160 }
    }

    return [pscustomobject]@{
        X = [int]($settingsWindow.Left + $relX)
        Y = [int]($settingsWindow.Top + $relY)
    }
}

function Invoke-ProjectSettingsFooterButton {
    param(
        [int]$ProcessId,
        [ValidateSet("Save", "Cancel", "PublishLocal", "Publish")]
        [string]$Button
    )

    $settingsWindow = Find-ProjectSettingsWindow -ProcessId $ProcessId -TimeoutSeconds 10
    if (-not $settingsWindow) {
        throw "Project Settings window was not found for '$Button'."
    }

    $buttonY = [int]($settingsWindow.Bottom - $settingsWindow.Top - 24)
    switch ($Button) {
        "Save" {
            $buttonX = [int]($settingsWindow.Right - $settingsWindow.Left - 57)
            $label = "Project Settings Save"
        }
        "Cancel" {
            $buttonX = [int]($settingsWindow.Right - $settingsWindow.Left - 162)
            $label = "Project Settings Cancel"
        }
        "PublishLocal" {
            $buttonX = 57
            $label = "Publish Local"
        }
        "Publish" {
            $buttonX = 160
            $label = "Publish"
        }
    }

    Invoke-ProjectSettingsRelativeClick -ProcessId $ProcessId -X $buttonX -Y $buttonY -Label $label
}

function Wait-ProjectSettingsClosed {
    param(
        [int]$ProcessId,
        [int]$TimeoutSeconds = 20
    )

    $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
    do {
        if (-not (Find-ProjectSettingsWindow -ProcessId $ProcessId -TimeoutSeconds 1)) {
            return $true
        }

        Start-Sleep -Seconds 1
    } while ((Get-Date) -lt $deadline)

    return $false
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

    # Wait for the browser window to appear (it is a separate popup from the main window)
    $browser = $null
    $browserAppearDeadline = (Get-Date).AddSeconds(30)
    do {
        $browser = Find-BrowserWindow -ProcessId $ProcessId
        if ($browser) { break }
        Start-Sleep -Seconds 2
    } while ((Get-Date) -lt $browserAppearDeadline)

    if ($browser) {
        Write-Diagnostic "Using project browser bounds $($browser.Left),$($browser.Top),$($browser.Right),$($browser.Bottom)."
        [Bg3PublishWin32]::ShowWindow($browser.Handle, [Bg3PublishWin32]::SW_RESTORE) | Out-Null
        [Bg3PublishWin32]::BringWindowToTop($browser.Handle) | Out-Null
        [Bg3PublishWin32]::SetForegroundWindow($browser.Handle) | Out-Null

        # Wait for the project list inside the browser to populate before clicking
        $null = Wait-ForBrowserContent -Browser $browser -TimeoutSeconds 90 -MinDescendantCount 15

        # Re-bring browser to foreground after the content wait
        [Bg3PublishWin32]::ShowWindow($browser.Handle, [Bg3PublishWin32]::SW_RESTORE) | Out-Null
        [Bg3PublishWin32]::BringWindowToTop($browser.Handle) | Out-Null
        [Bg3PublishWin32]::SetForegroundWindow($browser.Handle) | Out-Null

        $searchX = [int]($browser.Right - 340)
        $searchY = [int]($browser.Top + 85)
        $cardX = [int]($browser.Left + ($browser.Width / 2))
        $cardY = [int]($browser.Top + 228)
        $selectX = [int]($browser.Right - 62)
        $selectY = [int]($browser.Bottom - 32)
    } else {
        $screen = [System.Windows.Forms.Screen]::PrimaryScreen.Bounds
        Write-Diagnostic "Browser window not found after 30s; using screen fallback $($screen.Width)x$($screen.Height)."
        $searchX = [int]($screen.Width * 0.64)
        $searchY = 170
        $cardX = [int]($screen.Width * 0.50)
        $cardY = 312
        $selectX = [int]($screen.Width - 420)
        $selectY = [int]($screen.Height - 175)
    }

    Write-Diagnostic "Clicking 'Project browser search' at absolute coordinates $searchX,$searchY."
    Invoke-MouseClick -X $searchX -Y $searchY
    Start-Sleep -Milliseconds 300
    Send-KeyToForeground -Key "^(a)"
    Start-Sleep -Milliseconds 100

    $searchText = if ($ProjectName) { $ProjectName } else { $ProjectPath }
    Write-Diagnostic "Pasting search text via clipboard: '$searchText'."
    Add-Type -AssemblyName System.Windows.Forms
    [System.Windows.Forms.Clipboard]::SetText($searchText)
    Send-KeyToForeground -Key "^v"
    Start-Sleep -Seconds 5
    Write-Diagnostic "Search text sent; waiting for filter to apply."

    Write-Diagnostic "Clicking 'Project card' at absolute coordinates $cardX,$cardY."
    Invoke-MouseClick -X $cardX -Y $cardY
    Start-Sleep -Milliseconds 500

    # Check if Select button is enabled using FromPoint (avoids stale-handle errors from FromHandle).
    # Retry the card click if Select button remains disabled.
    $selectEnabled = $false
    $retryDeadline = (Get-Date).AddSeconds(25)
    do {
        try {
            # Log what element is under the card coordinates
            $cardPoint = New-Object System.Windows.Point($cardX, $cardY)
            $elemAtCard = [System.Windows.Automation.AutomationElement]::FromPoint($cardPoint)
            if ($elemAtCard) {
                Write-Diagnostic "Element at card ($cardX,$cardY): Name='$($elemAtCard.Current.Name)' Type=$($elemAtCard.Current.ControlType.ProgrammaticName)."
            }

            # Check if Select button is enabled
            $selectPoint = New-Object System.Windows.Point($selectX, $selectY)
            $elemAtSelect = [System.Windows.Automation.AutomationElement]::FromPoint($selectPoint)
            if ($elemAtSelect -and $elemAtSelect.Current.Name -eq "Select" -and $elemAtSelect.Current.IsEnabled) {
                $selectEnabled = $true
                Write-Diagnostic "Project card selected (Select button is enabled)."
            } else {
                $sName = if ($elemAtSelect) { $elemAtSelect.Current.Name } else { "(not found)" }
                $sEnabled = if ($elemAtSelect) { "$($elemAtSelect.Current.IsEnabled)" } else { "n/a" }
                Write-Diagnostic "Select button: Name='$sName' IsEnabled=$sEnabled."
            }
        } catch {
            Write-Diagnostic "UIA FromPoint error: $($_.Exception.Message)"
        }
        if (-not $selectEnabled) {
            Write-Diagnostic "Retrying card click at $cardX,$cardY."
            Invoke-MouseClick -X $cardX -Y $cardY
            Start-Sleep -Seconds 2
        }
    } while (-not $selectEnabled -and (Get-Date) -lt $retryDeadline)

    if (-not $selectEnabled) {
        Write-Diagnostic "Could not confirm card selection via UIA; clicking Select anyway."
    }

    Write-Diagnostic "Clicking 'Select project button' at absolute coordinates $selectX,$selectY."
    Invoke-MouseClick -X $selectX -Y $selectY

    $waitStart = Get-Date
    $waitDeadline = $waitStart.AddSeconds(30)
    $projectWindowFound = $false
    do {
        Start-Sleep -Seconds 1
        $allGlasses = @(Get-Process -Name "Glasses" -ErrorAction SilentlyContinue)
        $elapsed = [int]((Get-Date) - $waitStart).TotalSeconds
        foreach ($g in $allGlasses) {
            $windows = @(Get-VisibleWindowSnapshot -ProcessId $g.Id)
            $match = $windows | Where-Object { $_.Title -like "*$ProjectName*" } | Select-Object -First 1
            if ($match) {
                Write-Diagnostic "[$($elapsed)s post-Select] Project window detected pid=$($g.Id) title='$($match.Title)' — exiting wait loop."
                $projectWindowFound = $true
                break
            }
        }
        if ($projectWindowFound) { break }
    } while ((Get-Date) -lt $waitDeadline)
    if (-not $projectWindowFound) {
        Write-Diagnostic "[30s post-Select] Project window not detected within budget — falling through to Find-ToolkitWindow."
    }
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

    Invoke-ToolkitRelativeClick -ProcessId $ProcessId -X 255 -Y 47 -Label "Project menu"
    Start-Sleep -Seconds 1
    Invoke-ToolkitRelativeClick -ProcessId $ProcessId -X 320 -Y 70 -Label "Project Settings menu item"

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

function Wait-ForLocalPublish {
    param(
        [string]$ProjectPath,
        [datetime]$StartedAt,
        [int]$TimeoutSeconds
    )

    if (-not $ProjectPath) {
        return $false
    }

    $projectRoot = Split-Path -Parent $ProjectPath
    $modsRoot = Split-Path -Parent $projectRoot
    if (-not (Test-Path -LiteralPath $modsRoot)) {
        Write-Diagnostic "BG3 Mods root was not found for local publish detection: $modsRoot"
        return $false
    }

    $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
    do {
        $pak = Get-ChildItem -LiteralPath $modsRoot -Filter "*.pak" -File -ErrorAction SilentlyContinue |
            Where-Object { $_.LastWriteTime -ge $StartedAt } |
            Sort-Object LastWriteTime -Descending |
            Select-Object -First 1
        if ($pak) {
            Write-Diagnostic "Detected local publish package: $($pak.FullName)"
            return $true
        }

        Start-Sleep -Seconds 2
    } while ((Get-Date) -lt $deadline)

    return $false
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

# Close any lingering Glasses instances before starting a fresh one.
# An existing instance causes a "Can't run 2 editor instances" dialog on the new PID,
# which the window-detection loop never catches (dialog is too small).
$existingGlasses = @(Get-Process -Name "Glasses" -ErrorAction SilentlyContinue |
    Where-Object { $_.Path -and ([System.IO.Path]::GetFullPath($_.Path) -eq $resolvedBg3ToolPath) })
if ($existingGlasses.Count -gt 0) {
    Write-Diagnostic "Found $($existingGlasses.Count) existing Glasses instance(s); closing before fresh start."
    foreach ($eg in $existingGlasses) {
        Write-Diagnostic "Closing existing Glasses pid=$($eg.Id) title='$($eg.MainWindowTitle)'."
        $eg.CloseMainWindow() | Out-Null
    }
    $closeDeadline = (Get-Date).AddSeconds(10)
    do {
        Start-Sleep -Seconds 1
        $existingGlasses = @(Get-Process -Name "Glasses" -ErrorAction SilentlyContinue |
            Where-Object { $_.Path -and ([System.IO.Path]::GetFullPath($_.Path) -eq $resolvedBg3ToolPath) })
    } while ($existingGlasses.Count -gt 0 -and (Get-Date) -lt $closeDeadline)
    foreach ($eg in @(Get-Process -Name "Glasses" -ErrorAction SilentlyContinue |
            Where-Object { $_.Path -and ([System.IO.Path]::GetFullPath($_.Path) -eq $resolvedBg3ToolPath) })) {
        Write-Diagnostic "Force-killing lingering Glasses pid=$($eg.Id)."
        $eg | Stop-Process -Force -ErrorAction SilentlyContinue
    }
    Start-Sleep -Seconds 2
}

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
    Write-Diagnostic "Toolkit initial window detected."

    if ($ProjectPath) {
        Write-Diagnostic "Using browser coordinate fallback for Toolkit project selection."
        Select-ToolkitProjectFromBrowser -Window $window -ProcessId $process.Id -ProjectName $ProjectName -ProjectPath $ProjectPath
        $toolkitSession = Find-ToolkitWindow -Path $resolvedBg3ToolPath -TimeoutSeconds 45 -ProjectName $ProjectName
        if (-not $toolkitSession) {
            Write-Diagnostic "Project-name window search timed out; falling back to any Toolkit window by path."
            $toolkitSession = Find-ToolkitWindow -Path $resolvedBg3ToolPath -TimeoutSeconds 20
        }
        if (-not $toolkitSession) {
            Write-Diagnostic "Path-matched search timed out; trying any Glasses process regardless of path."
            $deadline = (Get-Date).AddSeconds(15)
            do {
                $anyGlasses = Get-Process -Name "Glasses" -ErrorAction SilentlyContinue |
                    Sort-Object StartTime -Descending | Select-Object -First 1
                if ($anyGlasses) {
                    Write-Diagnostic "Found Glasses pid=$($anyGlasses.Id) path='$($anyGlasses.Path)'."
                    $anyWindow = Find-WindowByProcessId -ProcessId $anyGlasses.Id -TimeoutSeconds 10
                    if ($anyWindow) {
                        $toolkitSession = @{ Process = $anyGlasses; Window = $anyWindow }
                        break
                    }
                }
                Start-Sleep -Seconds 2
            } while ((Get-Date) -lt $deadline)
        }
        if (-not $toolkitSession) {
            throw "Toolkit main window was not found after coordinate project selection."
        }
        $process = $toolkitSession.Process
        $window = $toolkitSession.Window
        if (-not (Dismiss-LevelSelector -ProcessId $process.Id -TimeoutSeconds 60)) {
            throw "Toolkit level selector browser did not close after coordinate project selection."
        }
    }

    Open-ProjectSettings -Window $window -ProcessId $process.Id

    if (-not (Find-ProjectSettingsWindow -ProcessId $process.Id -TimeoutSeconds 30)) {
        throw "Project Settings window did not open."
    }

    Invoke-ProjectSettingsFooterButton -ProcessId $process.Id -Button Save
    Start-Sleep -Seconds 8

    if (-not (Find-ProjectSettingsWindow -ProcessId $process.Id -TimeoutSeconds 3)) {
        Write-Diagnostic "Project Settings closed after Save; reopening."
        $window = Find-WindowByProcessId -ProcessId $process.Id -TimeoutSeconds 60
        Open-ProjectSettings -Window $window -ProcessId $process.Id
        if (-not (Find-ProjectSettingsWindow -ProcessId $process.Id -TimeoutSeconds 30)) {
            throw "Project Settings window did not reopen after Save."
        }
    }

    Invoke-ProjectSettingsFooterButton -ProcessId $process.Id -Button PublishLocal
    $localPublishTimeout = [Math]::Min($TimeoutSeconds, 180)
    $localPublishSucceeded = Wait-ForLocalPublish -ProjectPath $ProjectPath -StartedAt $startedAt -TimeoutSeconds $localPublishTimeout
    if (-not $localPublishSucceeded) {
        $localPublishSucceeded = Wait-ForLogSuccess -ToolkitDirectory $toolkitDirectory -StartedAt $startedAt -TimeoutSeconds $localPublishTimeout
    }
    if (-not $localPublishSucceeded) {
        throw "Toolkit did not report a successful local publish. Diagnostic log: $script:DiagnosticPath"
    }

    Minimize-OtherWindows -KeepProcessId $process.Id
    Set-ToolkitForeground -ProcessId $process.Id

    if (-not (Find-ProjectSettingsWindow -ProcessId $process.Id -TimeoutSeconds 5)) {
        Open-ProjectSettings -Window $window -ProcessId $process.Id
        if (-not (Find-ProjectSettingsWindow -ProcessId $process.Id -TimeoutSeconds 30)) {
            throw "Project Settings window did not reopen before Publish."
        }
    }

    $publishCoords = Get-ProjectSettingsFooterButtonCoords -ProcessId $process.Id -Button Publish
    if (-not (Wait-ForPublishButtonEnabled -ButtonX $publishCoords.X -ButtonY $publishCoords.Y -TimeoutSeconds 60)) {
        throw "Publish button never became enabled within 60s after PublishLocal."
    }
    Write-Diagnostic "Publish button enabled — clicking."
    Invoke-ProjectSettingsFooterButton -ProcessId $process.Id -Button Publish

    if (-not (Wait-ForUploadHandoff -ToolkitDirectory $toolkitDirectory -StartedAt $startedAt -TimeoutSeconds $TimeoutSeconds)) {
        throw "Toolkit did not hand off a new upload to mod.io within $TimeoutSeconds seconds. Diagnostic log: $script:DiagnosticPath"
    }

    Write-Diagnostic "Toolkit upload handoff completed; API finalization should verify scan and live status."
} catch {
    Write-Diagnostic "GUI automation failed: $($_.Exception.GetType().FullName): $($_.Exception.Message)"
    if ($_.ScriptStackTrace) {
        Write-Diagnostic "PowerShell stack: $($_.ScriptStackTrace)"
    }
    throw
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
