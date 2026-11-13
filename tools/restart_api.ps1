Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -match 'uvicorn' } | ForEach-Object {
  Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue
}
Start-Sleep -Seconds 2
# BENCH RELAXATION (dev server only, documented in PROGRESS.md): indoor GPS
# providers idle after the registration burst, so the raid gate's 30 s fix
# freshness cannot be met at the bench. 15 min lets the raid chain be tested
# end to end with honest (older) fixes. Test suite + product behavior keep 30 s.
$env:CM_RAID_FIX_MAX_AGE_MS = '900000'
# Bench geofence (dev server only): the explore quest needs a configured
# outdoor area; the bench 'landmark' is the room, so point the demo
# geofence at it. Production/demo deployments configure their own.
$env:CM_GEOFENCE_LAT = '1.4335105'
$env:CM_GEOFENCE_LON = '103.7766169'
$env:CM_GEOFENCE_RADIUS_M = '200'
Start-Process -WindowStyle Hidden -FilePath 'D:\catch_me\backend\.venv\Scripts\python.exe' -ArgumentList '-m','uvicorn','app.main:app','--host','0.0.0.0','--port','8000' -WorkingDirectory 'D:\catch_me\backend'
Write-Output "relaunched"
