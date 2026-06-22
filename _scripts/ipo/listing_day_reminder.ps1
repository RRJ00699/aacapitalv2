$env:DATABASE_URL = "postgresql://neondb_owner:npg_CU4meJPwa8Gn@ep-small-river-apqw6vg6-pooler.c-7.us-east-1.aws.neon.tech/neondb?sslmode=require&channel_binding=require"
Set-Location "C:\aacapital-v2"

# Check for listing day IPOs
$today = (Get-Date).ToString("yyyy-MM-dd")
$result = python - << 'PY'
import os, psycopg2
conn = psycopg2.connect(os.environ['DATABASE_URL'])
cur = conn.cursor()
cur.execute("SELECT company_name, symbol FROM ipo_intelligence WHERE listing_date = CURRENT_DATE AND symbol IS NOT NULL")
rows = cur.fetchall()
for r in rows:
    print(f"{r[0]}|{r[1]}")
conn.close()
PY

if ($result) {
    foreach ($line in $result -split "
") {
        if ($line.Trim()) {
            $parts = $line.Split("|")
            $company = $parts[0]; $symbol = $parts[1]
            Write-Host "IPO LISTING TODAY: $company ($symbol)"
            
            # Show Windows notification
            Add-Type -AssemblyName System.Windows.Forms
            [System.Windows.Forms.MessageBox]::Show(
                "IPO LISTING TODAY: $company ($symbol)

Run:
python _scripts\ipo\listing_day_monitor.py --symbol $symbol",
                "AACapital â€” IPO Listing Alert",
                [System.Windows.Forms.MessageBoxButtons]::OK,
                [System.Windows.Forms.MessageBoxIcon]::Information
            ) | Out-Null
        }
    }
}
