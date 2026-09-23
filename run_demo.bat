@echo off
setlocal
REM ScholarGraph VN - click-to-run demo (SG-041).
REM 1) Kiem tra moi truong + offline smoke, 2) mo API server, 3) mo trinh duyet.
cd /d "%~dp0scholargraph"
if not exist ".venv\Scripts\python.exe" (
  echo FAIL: khong thay .venv - xem docs/REPRODUCE.md muc 1.
  pause
  exit /b 1
)

echo == [1/2] Demo checks (offline, khong mang) ==
powershell -ExecutionPolicy Bypass -File scripts\run_demo.ps1
if errorlevel 1 (
  echo DEMO FAILED - xem loi o tren.
  pause
  exit /b 1
)

echo.
echo == [2/2] Khoi dong API server (cua so rieng) ==
start "ScholarGraph API - dong cua so nay de tat server" cmd /k "set PYTHONPATH=src && .venv\Scripts\python.exe -m uvicorn scholargraph.api.app:app --host 127.0.0.1 --port 8000"
echo Cho server nap model (lan dau co the >1 phut, toi da cho 4 phut)...
powershell -NoProfile -Command "$ok=$false; for ($i=0; $i -lt 48; $i++) { try { $h=Invoke-RestMethod -Uri 'http://127.0.0.1:8000/health' -TimeoutSec 5; if ($h.status -eq 'ok') { $ok=$true; break } } catch { Start-Sleep -Seconds 5 } }; if (-not $ok) { Write-Error 'FAIL: server chua san sang sau 4 phut - xem cua so ScholarGraph API'; exit 1 }; Write-Output ('Server OK: ' + $h.docs + ' docs, model ' + $h.model_revision)"
if errorlevel 1 (
  echo Server chua san sang - kiem tra cua so "ScholarGraph API" roi Enter de thu lai.
  pause
  exit /b 1
)
start http://127.0.0.1:8000/
echo.
echo Trinh duyet: http://127.0.0.1:8000/  (neu trang trang, doi 30s roi F5)
echo Kich ban 5 phut: docs/DEMO_SCRIPT.md
echo Tat server: dong cua so "ScholarGraph API".
echo.
pause
