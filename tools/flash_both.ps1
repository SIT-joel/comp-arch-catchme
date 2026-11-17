# Kill the crash loggers and flash both boards in one tight sequence
# (the loggers respawn from a watcher; the upload must win the race).
param(
  [Parameter(Mandatory = $true)][string]$D1Dir,
  [Parameter(Mandatory = $true)][string]$D2Dir
)
$cli = "D:/catch_me/tools/arduino-cli/bin/arduino-cli.exe"
$cfg = "D:/catch_me/tools/arduino-cli/arduino-cli.yaml"

function Kill-Loggers {
  for ($i = 0; $i - 6; $i++) {
    $procs = Get-CimInstance Win32_Process -Filter "Name = 'python.exe'" |
      Where-Object { $_.CommandLine -match 'crash_logger' }
    if (-not $procs) { return }
    $procs | ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }
    Start-Sleep -Milliseconds 300
  }
}

Kill-Loggers
& $cli --config-file $cfg upload --fqbn TinyCircuits:samd:tinyscreen --input-dir $D1Dir -p COM3 2>&1 | Select-Object -Last 1
Kill-Loggers
& $cli --config-file $cfg upload --fqbn TinyCircuits:samd:tinyscreen --input-dir $D2Dir -p COM7 2>&1 | Select-Object -Last 1

# Restart one logger per port for the bench.
Start-Process -WindowStyle Hidden D:/catch_me/backend/.venv/Scripts/python.exe -ArgumentList 'tools/crash_logger.py', 'COM3', 'tools/crash_logs/b1_com3.log' -WorkingDirectory D:/catch_me
Start-Process -WindowStyle Hidden D:/catch_me/backend/.venv/Scripts/python.exe -ArgumentList 'tools/crash_logger.py', 'COM7', 'tools/crash_logs/b2_com7.log' -WorkingDirectory D:/catch_me
