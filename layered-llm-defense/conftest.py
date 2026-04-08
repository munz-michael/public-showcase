"""
pytest configuration for the showcase repo.

Adds the project root to sys.path so that `from lld.X import Y` works
without requiring `pip install -e .` first.
"""
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))
