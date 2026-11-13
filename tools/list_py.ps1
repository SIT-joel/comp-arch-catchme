Get-CimInstance Win32_Process |
  Where-Object { $_.Name -match 'python' } |
  ForEach-Object { "{0} {1} :: {2}" -f $_.ProcessId, $_.Name, $_.CommandLine }
