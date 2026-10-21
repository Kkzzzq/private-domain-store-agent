from types import SimpleNamespace
import os
import sys


def test_api_jobs_reuse_installed_quality_runtime(monkeypatch, tmp_path):
    from app.quality import worker
    monkeypatch.setattr(worker, 'settings', SimpleNamespace(backend_root=tmp_path / 'backend'))
    assert worker.child_python() == sys.executable
    candidate = tmp_path / 'qa-venv' / ('Scripts/python.exe' if os.name == 'nt' else 'bin/python')
    candidate.parent.mkdir(parents=True)
    candidate.write_text('test executable')
    candidate.chmod(0o755)
    assert worker.child_python() == str(candidate)
