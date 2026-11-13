Get-PnpDevice -PresentOnly |
  Where-Object { $_.InstanceId -like 'USB*' -and $_.Class -ne 'HIDClass' } |
  ForEach-Object { "{0} | {1} | {2}" -f $_.Status, $_.FriendlyName, $_.InstanceId }
