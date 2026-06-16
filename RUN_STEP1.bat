@echo off
echo Step 1: Returns Calculator (uses existing Kite candles in Neon)
for /f "tokens=1,2 delims==" %%a in (.env.local) do (set "%%a=%%b")
python _scripts\calculator_returns.py
pause
