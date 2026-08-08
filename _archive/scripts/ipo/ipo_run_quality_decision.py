import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

SCRIPTS = [
    ROOT / "_scripts" / "ipo" / "ipo_feature_store.py",
    ROOT / "_scripts" / "ipo" / "ipo_decision_engine.py",
]

for script in SCRIPTS:
    print()
    print("=" * 100)
    print(f"RUNNING: {script}")
    print("=" * 100)
    result = subprocess.run([sys.executable, str(script)], cwd=str(ROOT), text=True)
    if result.returncode != 0:
        raise SystemExit(result.returncode)

print()
print("IPO feature quality + decision pipeline completed successfully.")
