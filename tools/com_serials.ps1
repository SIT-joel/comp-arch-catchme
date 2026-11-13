Get-CimInstance Win32_SerialPort | Where-Object { $_.DeviceID -eq 'COM3' -or $_.DeviceID -eq 'COM4' } | ForEach-Object {
  "{0} {1}" -f $_.DeviceID, $_.PNPDeviceID
}
