@echo off
echo AACapital - IPO Pipeline Setup
echo ================================

REM Load env from .env.local
for /f "tokens=1,2 delims==" %%a in (.env.local) do (
    if not "%%a"=="" if not "%%b"=="" (
        set "%%a=%%b"
    )
)

REM Create folders
if not exist "_scripts\logs" mkdir "_scripts\logs"

REM Install deps
echo Installing Python packages...
pip install requests beautifulsoup4 lxml psycopg2-binary pandas openpyxl --quiet

echo.
echo Done! Now run:
echo   RUN_STEP1.bat   (returns calculator - fastest)
echo   RUN_STEP2.bat   (chittorgarh scraper)
echo   RUN_STEP3.bat   (GMP scraper)
echo   RUN_STEP4.bat   (anchor scraper)
echo.
