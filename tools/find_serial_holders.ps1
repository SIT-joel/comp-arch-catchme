Get-CimInstance Win32_Process |
  Where-Object { $_.CommandLine -match 'read_serial' } |
  ForEach-Object { "{0} {1}" -f $_.ProcessId, $_.Name }
