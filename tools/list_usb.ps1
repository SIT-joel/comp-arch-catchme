Get-PnpDevice -PresentOnly |
  Where-Object { $_.InstanceId -like 'USB*' } |
  ForEach-Object { "{0} | {1}" -f $_.Status, $_.FriendlyName }
