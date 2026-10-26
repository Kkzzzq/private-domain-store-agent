import shutil
import subprocess
from pathlib import Path

import pytest


def test_sku_save_button_submits_after_parameter_editor_removed():
    node = shutil.which("node")
    if not node:
        pytest.skip("Node runtime unavailable")
    root = Path(__file__).resolve().parents[2]
    result = subprocess.run([node, "backend/scripts/test_catalog_buttons.cjs"], cwd=root,
                            capture_output=True, text=True, timeout=15)
    assert result.returncode == 0, result.stdout + result.stderr
