@echo off
echo Step 3: GMP History Scraper
for /f "tokens=1,2 delims==" %%a in (.env.local) do (set "%%a=%%b")
python _scripts\scraper_gmp.py
pause
