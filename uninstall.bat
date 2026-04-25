@echo off
setlocal
echo Removing Decypher from startup...
powershell -NoProfile -ExecutionPolicy Bypass -Command "$startup = Join-Path $env:APPDATA 'Microsoft\Windows\Start Menu\Programs\Startup'; $removed = $false; foreach ($name in 'run_decypher.vbs','Decypher.lnk') { $path = Join-Path $startup $name; if (Test-Path -LiteralPath $path) { Remove-Item -LiteralPath $path -Force; $removed = $true } }; if ($removed) { Write-Host 'Startup entry removed.' } else { Write-Host 'No startup entry found.' }"
echo.
echo Done. You can delete this folder now.
endlocal
pause
