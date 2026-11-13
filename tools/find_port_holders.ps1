Get-CimInstance Win32_Process |
  Where-Object { $_.Name -match 'bossac|arduino|python|putty' } |
  ForEach-Object {
    $cl = if ($_.CommandLine) { $_.CommandLine.Substring(0, [Math]::Min(140, $_.CommandLine.Length)) } else { '' }
    "{0} {1} :: {2}" -f $_.ProcessId, $_.Name, $cl
  }
