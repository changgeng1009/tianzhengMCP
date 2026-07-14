[CmdletBinding()]
param(
    [switch]$Execute,
    [switch]$TestNow
)

Set-StrictMode -Version 2.0
$ErrorActionPreference = 'Stop'

$TaskName = 'Resume-Codex-Goal-Once'
$RunHour = 5
$RunMinute = 18

$LogDirectory = Join-Path $env:LOCALAPPDATA 'CodexGoalResume'
$LogFile = Join-Path $LogDirectory 'resume.log'

New-Item -ItemType Directory -Path $LogDirectory -Force | Out-Null

function Write-Log {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Message
    )

    $line = '[{0}] {1}' -f (Get-Date -Format 'yyyy-MM-dd HH:mm:ss'), $Message
    Add-Content -LiteralPath $LogFile -Value $line -Encoding UTF8
}

function Register-OneTimeTask {
    $now = Get-Date
    $runAt = $now.Date.AddHours($RunHour).AddMinutes($RunMinute)

    if ($runAt -le $now) {
        $runAt = $runAt.AddDays(1)
    }

    $scriptPath = $PSCommandPath
    if ([string]::IsNullOrWhiteSpace($scriptPath)) {
        throw 'The script must be run from a .ps1 file.'
    }

    $powershellExe = Join-Path $PSHOME 'powershell.exe'
    if (-not (Test-Path -LiteralPath $powershellExe)) {
        $powershellExe = 'powershell.exe'
    }

    $arguments = '-NoProfile -ExecutionPolicy Bypass -File "{0}" -Execute' -f $scriptPath

    $action = New-ScheduledTaskAction `
        -Execute $powershellExe `
        -Argument $arguments

    $trigger = New-ScheduledTaskTrigger `
        -Once `
        -At $runAt

    $currentUser = [System.Security.Principal.WindowsIdentity]::GetCurrent().Name

    $principal = New-ScheduledTaskPrincipal `
        -UserId $currentUser `
        -LogonType Interactive `
        -RunLevel Limited

    $settings = New-ScheduledTaskSettingsSet `
        -StartWhenAvailable `
        -AllowStartIfOnBatteries `
        -DontStopIfGoingOnBatteries `
        -WakeToRun `
        -ExecutionTimeLimit (New-TimeSpan -Minutes 5)

    Unregister-ScheduledTask `
        -TaskName $TaskName `
        -Confirm:$false `
        -ErrorAction SilentlyContinue

    Register-ScheduledTask `
        -TaskName $TaskName `
        -Action $action `
        -Trigger $trigger `
        -Principal $principal `
        -Settings $settings `
        -Description 'Resume the current Codex Goal once after quota reset.' `
        -Force | Out-Null

    Write-Log ('Task registered for {0}' -f $runAt.ToString('yyyy-MM-dd HH:mm:ss'))

    Write-Host ''
    Write-Host 'One-time task created.'
    Write-Host ('Run time: {0}' -f $runAt.ToString('yyyy-MM-dd HH:mm:ss'))
    Write-Host ('Task name: {0}' -f $TaskName)
    Write-Host ('Log file: {0}' -f $LogFile)
    Write-Host ''
    Write-Host 'Keep Windows signed in, unlocked, and keep the Codex goal page open.'
}

function Add-NativeTypes {
    Add-Type -AssemblyName UIAutomationClient
    Add-Type -AssemblyName UIAutomationTypes

    if ($null -eq ('CodexGoalNative' -as [type])) {
        $nativeCode = @'
using System;
using System.Runtime.InteropServices;

public static class CodexGoalNative
{
    [DllImport("user32.dll")]
    [return: MarshalAs(UnmanagedType.Bool)]
    public static extern bool ShowWindowAsync(IntPtr hWnd, int nCmdShow);

    [DllImport("user32.dll")]
    [return: MarshalAs(UnmanagedType.Bool)]
    public static extern bool SetForegroundWindow(IntPtr hWnd);

    [DllImport("user32.dll")]
    [return: MarshalAs(UnmanagedType.Bool)]
    public static extern bool SetCursorPos(int X, int Y);

    [DllImport("user32.dll")]
    public static extern void mouse_event(
        uint dwFlags,
        uint dx,
        uint dy,
        uint dwData,
        UIntPtr dwExtraInfo
    );
}
'@

        Add-Type -TypeDefinition $nativeCode -Language CSharp
    }
}

function Get-ElementText {
    param(
        [Parameter(Mandatory = $true)]
        [System.Windows.Automation.AutomationElement]$Element
    )

    $parts = New-Object System.Collections.Generic.List[string]

    try {
        if (-not [string]::IsNullOrWhiteSpace($Element.Current.Name)) {
            $parts.Add([string]$Element.Current.Name)
        }
    }
    catch {
    }

    try {
        if (-not [string]::IsNullOrWhiteSpace($Element.Current.HelpText)) {
            $parts.Add([string]$Element.Current.HelpText)
        }
    }
    catch {
    }

    try {
        if (-not [string]::IsNullOrWhiteSpace($Element.Current.AutomationId)) {
            $parts.Add([string]$Element.Current.AutomationId)
        }
    }
    catch {
    }

    try {
        if (-not [string]::IsNullOrWhiteSpace($Element.Current.ClassName)) {
            $parts.Add([string]$Element.Current.ClassName)
        }
    }
    catch {
    }

    return ($parts -join ' ')
}

function Invoke-MouseClick {
    param(
        [Parameter(Mandatory = $true)]
        [int]$X,

        [Parameter(Mandatory = $true)]
        [int]$Y
    )

    [CodexGoalNative]::SetCursorPos($X, $Y) | Out-Null
    Start-Sleep -Milliseconds 250

    [CodexGoalNative]::mouse_event(
        0x0002,
        0,
        0,
        0,
        [UIntPtr]::Zero
    )

    Start-Sleep -Milliseconds 100

    [CodexGoalNative]::mouse_event(
        0x0004,
        0,
        0,
        0,
        [UIntPtr]::Zero
    )
}

function Find-GoalWindow {
    $allProcesses = @(
        Get-Process |
            Where-Object {
                $_.MainWindowHandle -ne 0
            }
    )

    $preferred = @(
        $allProcesses |
            Where-Object {
                $_.ProcessName -match 'ChatGPT|Codex|OpenAI' -or
                $_.MainWindowTitle -match 'ChatGPT|Codex|OpenAI'
            }
    )

    $other = @(
        $allProcesses |
            Where-Object {
                $preferred.Id -notcontains $_.Id
            }
    )

    $candidates = @($preferred + $other)

    foreach ($process in $candidates) {
        try {
            $root = [System.Windows.Automation.AutomationElement]::FromHandle(
                [IntPtr]$process.MainWindowHandle
            )

            if ($null -eq $root) {
                continue
            }

            $elements = $root.FindAll(
                [System.Windows.Automation.TreeScope]::Descendants,
                [System.Windows.Automation.Condition]::TrueCondition
            )

            foreach ($element in $elements) {
                $text = Get-ElementText -Element $element

                if ($text -like '*goal-objective.md*') {
                    return [pscustomobject]@{
                        Process = $process
                        Root = $root
                        Anchor = $element
                        Elements = $elements
                    }
                }
            }
        }
        catch {
            continue
        }
    }

    return $null
}

function Find-GoalCard {
    param(
        [Parameter(Mandatory = $true)]
        [System.Windows.Automation.AutomationElement]$Anchor
    )

    $walker = [System.Windows.Automation.TreeWalker]::RawViewWalker
    $current = $Anchor
    $best = $null
    $bestArea = [double]::MaxValue

    for ($i = 0; $i -lt 10; $i++) {
        try {
            $current = $walker.GetParent($current)
        }
        catch {
            break
        }

        if ($null -eq $current) {
            break
        }

        try {
            $rect = $current.Current.BoundingRectangle
        }
        catch {
            continue
        }

        if (
            $rect.Width -ge 500 -and
            $rect.Height -ge 80 -and
            $rect.Height -le 320
        ) {
            $area = $rect.Width * $rect.Height

            if ($area -lt $bestArea) {
                $best = $current
                $bestArea = $area
            }
        }
    }

    return $best
}

function Find-ResumeButton {
    param(
        [Parameter(Mandatory = $true)]
        [System.Windows.Automation.AutomationElement]$Card
    )

    $cardRect = $Card.Current.BoundingRectangle

    $elements = $Card.FindAll(
        [System.Windows.Automation.TreeScope]::Descendants,
        [System.Windows.Automation.Condition]::TrueCondition
    )

    $buttons = New-Object System.Collections.Generic.List[object]

    foreach ($element in $elements) {
        try {
            if ($element.Current.ControlType -ne [System.Windows.Automation.ControlType]::Button) {
                continue
            }

            if (-not $element.Current.IsEnabled) {
                continue
            }

            $rect = $element.Current.BoundingRectangle

            if (
                $rect.Width -le 0 -or
                $rect.Height -le 0 -or
                $rect.Width -gt 120 -or
                $rect.Height -gt 120
            ) {
                continue
            }

            $buttons.Add(
                [pscustomobject]@{
                    Element = $element
                    Rect = $rect
                    Text = Get-ElementText -Element $element
                }
            )
        }
        catch {
            continue
        }
    }

    foreach ($button in $buttons) {
        if ($button.Text -match 'resume|continue|play|start|run') {
            return $button
        }
    }

    $headerButtons = @(
        $buttons |
            Where-Object {
                $centerY = $_.Rect.Top + ($_.Rect.Height / 2)

                $centerY -ge $cardRect.Top -and
                $centerY -le ($cardRect.Top + [Math]::Min(90, $cardRect.Height * 0.55)) -and
                $_.Rect.Left -ge ($cardRect.Left + ($cardRect.Width * 0.55))
            } |
            Sort-Object {
                $_.Rect.Left
            }
    )

    Write-Log ('Header button count: {0}' -f $headerButtons.Count)

    foreach ($button in $headerButtons) {
        Write-Log (
            'Button X={0} Y={1} W={2} H={3} Text={4}' -f
            [int]$button.Rect.Left,
            [int]$button.Rect.Top,
            [int]$button.Rect.Width,
            [int]$button.Rect.Height,
            $button.Text
        )
    }

    if ($headerButtons.Count -ge 3) {
        return $headerButtons[1]
    }

    return $null
}

function Invoke-ResumeButton {
    param(
        [Parameter(Mandatory = $true)]
        $Button
    )

    $element = $Button.Element

    try {
        $invokePattern = [System.Windows.Automation.InvokePattern]$element.GetCurrentPattern(
            [System.Windows.Automation.InvokePattern]::Pattern
        )

        $invokePattern.Invoke()
        Write-Log 'Resume button invoked through InvokePattern.'
        return $true
    }
    catch {
        Write-Log ('InvokePattern failed: {0}' -f $_.Exception.Message)
    }

    try {
        $legacyPattern = [System.Windows.Automation.LegacyIAccessiblePattern]$element.GetCurrentPattern(
            [System.Windows.Automation.LegacyIAccessiblePattern]::Pattern
        )

        $legacyPattern.DoDefaultAction()
        Write-Log 'Resume button invoked through LegacyIAccessiblePattern.'
        return $true
    }
    catch {
        Write-Log ('Legacy action failed: {0}' -f $_.Exception.Message)
    }

    try {
        $rect = $Button.Rect
        $x = [int]($rect.Left + ($rect.Width / 2))
        $y = [int]($rect.Top + ($rect.Height / 2))

        Invoke-MouseClick -X $x -Y $y
        Write-Log ('Resume button clicked at X={0}, Y={1}.' -f $x, $y)
        return $true
    }
    catch {
        Write-Log ('Mouse click on button failed: {0}' -f $_.Exception.Message)
    }

    return $false
}

function Invoke-CardFallbackClick {
    param(
        [Parameter(Mandatory = $true)]
        [System.Windows.Automation.AutomationElement]$Card
    )

    $rect = $Card.Current.BoundingRectangle

    if (
        $rect.Width -lt 500 -or
        $rect.Height -lt 80 -or
        $rect.Height -gt 320
    ) {
        throw 'The detected card rectangle is not safe for fallback clicking.'
    }

    $rightOffset = [Math]::Max(
        110,
        [Math]::Min(180, $rect.Width * 0.125)
    )

    $topOffset = [Math]::Max(
        24,
        [Math]::Min(48, $rect.Height * 0.22)
    )

    $x = [int]($rect.Right - $rightOffset)
    $y = [int]($rect.Top + $topOffset)

    Write-Log (
        'Using card fallback click at X={0}, Y={1}; card L={2}, T={3}, W={4}, H={5}' -f
        $x,
        $y,
        [int]$rect.Left,
        [int]$rect.Top,
        [int]$rect.Width,
        [int]$rect.Height
    )

    Invoke-MouseClick -X $x -Y $y
}

function Resume-CodexGoal {
    Add-NativeTypes

    Write-Log 'Searching for a window containing goal-objective.md.'

    $target = Find-GoalWindow

    if ($null -eq $target) {
        throw 'No visible window containing goal-objective.md was found.'
    }

    $process = $target.Process

    Write-Log (
        'Found process={0}, pid={1}, title={2}' -f
        $process.ProcessName,
        $process.Id,
        $process.MainWindowTitle
    )

    [CodexGoalNative]::ShowWindowAsync(
        [IntPtr]$process.MainWindowHandle,
        9
    ) | Out-Null

    Start-Sleep -Seconds 2

    [CodexGoalNative]::SetForegroundWindow(
        [IntPtr]$process.MainWindowHandle
    ) | Out-Null

    Start-Sleep -Seconds 2

    $card = Find-GoalCard -Anchor $target.Anchor

    if ($null -eq $card) {
        throw 'The goal card container could not be detected safely.'
    }

    $cardRect = $card.Current.BoundingRectangle

    Write-Log (
        'Goal card L={0}, T={1}, W={2}, H={3}' -f
        [int]$cardRect.Left,
        [int]$cardRect.Top,
        [int]$cardRect.Width,
        [int]$cardRect.Height
    )

    $resumeButton = Find-ResumeButton -Card $card

    if ($null -ne $resumeButton) {
        $success = Invoke-ResumeButton -Button $resumeButton

        if (-not $success) {
            throw 'A resume button was detected, but it could not be activated.'
        }
    }
    else {
        Write-Log 'No UI Automation resume button was found.'
        Invoke-CardFallbackClick -Card $card
    }

    Start-Sleep -Seconds 8
    Write-Log 'One-time resume action finished.'
}

if (-not $Execute -and -not $TestNow) {
    Register-OneTimeTask
    exit 0
}

try {
    Resume-CodexGoal
    Write-Host 'Resume action sent. Check the Codex window and the log file.'
    Write-Host ('Log file: {0}' -f $LogFile)
}
catch {
    Write-Log ('FAILED: {0}' -f $_.Exception.Message)
    Write-Error $_
}
finally {
    if ($Execute) {
        Unregister-ScheduledTask `
            -TaskName $TaskName `
            -Confirm:$false `
            -ErrorAction SilentlyContinue
    }
}
