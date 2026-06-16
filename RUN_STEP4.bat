@echo off
echo Step 4: Anchor Investor Scraper
for /f "tokens=1,2 delims==" %%a in (.env.local) do (set "%%a=%%b")
python _scripts\scraper_anchors.py
pause
