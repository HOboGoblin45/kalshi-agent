# create-shortcut.ps1 — Creates a "Kalshi Agent" desktop shortcut
# Run: powershell -ExecutionPolicy Bypass -File create-shortcut.ps1

$projectDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$batPath    = Join-Path $projectDir "start-kalshi.bat"
$iconPath   = Join-Path $projectDir "build" "icon.ico"
$desktop    = [Environment]::GetFolderPath("Desktop")
$lnkPath    = Join-Path $desktop "Kalshi Agent.lnk"

$shell = New-Object -ComObject WScript.Shell
$shortcut = $shell.CreateShortcut($lnkPath)
$shortcut.TargetPath       = $batPath
$shortcut.WorkingDirectory = $projectDir
$shortcut.Description      = "Kalshi Agent Terminal Dashboard"
$shortcut.WindowStyle      = 1  # Normal window

# Use custom icon if it exists, otherwise use cmd icon
if (Test-Path $iconPath) {
    $shortcut.IconLocation = $iconPath
}

$shortcut.Save()

Write-Host ""
Write-Host "  [OK] Desktop shortcut created: $lnkPath" -ForegroundColor Green
Write-Host "  Double-click 'Kalshi Agent' on your desktop to launch." -ForegroundColor Gray
Write-Host ""
