import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

SCRIPTS = [
    ROOT / "_scripts" / "ipo" / "ipo_live_feed.py",
    ROOT / "_scripts" / "ipo" / "ipo_similarity_engine.py",
    ROOT / "_scripts" / "ipo" / "ipo_listing_probability_engine.py",
]

for script in SCRIPTS:
    print()
    print("=" * 80)
    print(f"RUNNING: {script}")
    print("=" * 80)

    result = subprocess.run(
        [sys.executable, str(script)],
        cwd=str(ROOT),
        text=True,
    )

    if result.returncode != 0:
        raise SystemExit(result.returncode)

print()
print("IPO pipeline completed successfully.")
