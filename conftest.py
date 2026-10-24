"""Ensure the repo root is importable so `import src...` and `import config...`
work when running pytest from anywhere."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
