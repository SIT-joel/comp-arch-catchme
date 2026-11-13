$device = Get-PnpDevice | Where-Object { $_.FriendlyName -like '*COM5*' }
$device | ForEach-Object { Write-Output ("found: " + $_.InstanceId) }
if ($device) {
  Disable-PnpDevice -InstanceId $device.InstanceId -Confirm:$false
  Start-Sleep -Seconds 2
  Enable-PnpDevice -InstanceId $device.InstanceId -Confirm:$false
  Write-Output "re-enabled"
}
