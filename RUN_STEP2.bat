@echo off
echo Step 2: Chittorgarh Scraper (run overnight ~90 min)
for /f "tokens=1,2 delims==" %%a in (.env.local) do (set "%%a=%%b")
set IPO_EXCEL=aacapital_ipo_master_304.xlsx
python _scripts\scraper_chittorgarh.py
pause
