Get-CimInstance Win32_Process |
  Where-Object { $_.CommandLine -match 'COM5|serial' -and $_.Name -notmatch 'bash' } |
  ForEach-Object { "{0} {1} :: {2}" -f $_.ProcessId, $_.Name, $_.CommandLine }
