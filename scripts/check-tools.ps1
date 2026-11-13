<#
Read-only development prerequisite probe. No installs or configuration changes.
Run from any directory: powershell -NoProfile -File <path>\check-tools.ps1
#>
[CmdletBinding()]
param()

$ErrorActionPreference = 'Continue'
$script:MissingRequired = 0

function Test-Tool {
    param(
        [Parameter(Mandatory = $true)][string]$Label,
        [Parameter(Mandatory = $true)][string]$Command,
        [string[]]$VersionArguments = @('--version'),
        [bool]$Required = $true
    )

    $resolved = Get-Command $Command -CommandType Application -ErrorAction SilentlyContinue | Select-Object -First 1
    if (-not $resolved) {
        $kind = if ($Required) { 'MISSING' } else { 'OPTIONAL' }
        Write-Output ('[{0}] {1}: not on PATH' -f $kind, $Label)
        if ($Required) { $script:MissingRequired++ }
        return
    }

    try {
        $captured = @(& $resolved.Source @VersionArguments 2>&1)
        $resultCode = $LASTEXITCODE
        $versionLine = (($captured | ForEach-Object { ([string]$_).Replace([string][char]0, '') } | Select-Object -First 3) -join ' | ')
        if ($resultCode -eq 0) {
            Write-Output ('[OK] {0}: {1}' -f $Label, $versionLine)
        } else {
            Write-Output ('[CHECK] {0}: version probe exited {1}; {2}' -f $Label, $resultCode, $versionLine)
            if ($Required) { $script:MissingRequired++ }
        }
    } catch {
        Write-Output ('[CHECK] {0}: could not run version probe: {1}' -f $Label, $_.Exception.Message)
        if ($Required) { $script:MissingRequired++ }
    }
}

Write-Output 'Catch Me development tool check (read-only)'
Test-Tool -Label 'Git' -Command 'git'
Test-Tool -Label 'Node.js' -Command 'node'
Test-Tool -Label 'npm' -Command 'npm'

$pythonExecutable = Get-Command python3,python -CommandType Application -All -ErrorAction SilentlyContinue |
    Where-Object { $_.Source -notmatch '\\Microsoft\\WindowsApps\\' } | Select-Object -First 1
if ($pythonExecutable) {
    Test-Tool -Label 'Python 3' -Command $pythonExecutable.Source
} elseif (Get-Command 'py' -CommandType Application -ErrorAction SilentlyContinue) {
    Test-Tool -Label 'Python 3 (launcher)' -Command 'py' -VersionArguments @('-3', '--version')
} elseif (Get-Command 'python3' -CommandType Application -ErrorAction SilentlyContinue) {
    Test-Tool -Label 'Python 3' -Command 'python3'
} else {
    Test-Tool -Label 'Python' -Command 'python'
}

Test-Tool -Label 'Java/JDK (Android Studio may bundle it)' -Command 'java' -VersionArguments @('-version')
Test-Tool -Label 'ADB (may need SDK platform-tools on PATH)' -Command 'adb' -VersionArguments @('version')
Test-Tool -Label 'Docker client' -Command 'docker'
Test-Tool -Label 'Docker Compose v2' -Command 'docker' -VersionArguments @('compose', 'version')
Test-Tool -Label 'Arduino CLI (optional if using Arduino IDE)' -Command 'arduino-cli' -VersionArguments @('version') -Required $false
$gitExecutable = Get-Command git -CommandType Application -ErrorAction SilentlyContinue | Select-Object -First 1
$gitBash = if ($gitExecutable) { Join-Path (Split-Path (Split-Path $gitExecutable.Source -Parent) -Parent) 'bin\bash.exe' } else { $null }
if ($gitBash -and (Test-Path -LiteralPath $gitBash)) {
    Test-Tool -Label 'Git Bash (optional on Windows)' -Command $gitBash -Required $false
} else {
    Test-Tool -Label 'Bash (optional on Windows)' -Command 'bash' -Required $false
}

Write-Output ''
Write-Output 'Manual checks: Android Studio/SDK, TinyScreen+ board support, firmware libraries, two phones/devices, GLM access.'
Write-Output 'Docker version checks do not verify a running daemon. Version probes do not establish compatibility or hardware support.'
Write-Output ('Required command-line probes needing attention: {0}' -f $script:MissingRequired)
if ($script:MissingRequired -gt 0) { exit 1 }
exit 0
