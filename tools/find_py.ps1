Get-CimInstance Win32_Process |
  Where-Object { $_.Name -match 'python|putty|arduino|serial' } |
  ForEach-Object { "{0} {1} :: {2}" -f $_.ProcessId, $_.Name, ($_.CommandLine -replace '\s+',' ').Substring(0, [Math]::Min(120, $_.CommandLine.Length)) }
