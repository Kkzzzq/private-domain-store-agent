"""Compatibility entry: run from backend with python scripts/manage_operator.py."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.operations_cli import main

if __name__ == '__main__':
    main()
