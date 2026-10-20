import os
from pathlib import Path
from uuid import uuid4


def test_quality_uploads_use_private_web_tree_and_matching_recommendation_limit(tmp_path, monkeypatch):
    from app.core.config import Settings
    from app.quality.sandbox import configure_environment
    monkeypatch.setattr(os, 'environ', dict(os.environ))
    os.environ.update(QA_CHILD_RUN=uuid4().hex, QA_CHILD_WORKSPACE=str(tmp_path))
    configure_environment()
    settings = Settings()
    assert settings.web_dir == tmp_path / 'web'
    assert (settings.web_dir / 'op.html').is_file()
    assert not (settings.web_dir / 'covers' / 'uploads').exists()
    upload = settings.web_dir / 'covers' / 'uploads' / 'isolation-proof.png'
    upload.parent.mkdir(parents=True)
    upload.write_bytes(b'isolated upload')
    real = Path(__file__).resolve().parents[2] / 'web' / 'covers' / 'uploads' / upload.name
    assert not real.exists()
    assert settings.recommendation_max_steps == Settings.model_fields['recommendation_max_steps'].default == 6


def test_normal_web_requests_keep_the_business_web_root(monkeypatch):
    from app.core.config import Settings
    monkeypatch.delenv('QA_CHILD_RUN', raising=False)
    assert Settings().web_dir == Path(__file__).resolve().parents[2] / 'web'


def test_model_budget_exhaustion_stops_before_network_and_reports_limits(monkeypatch):
    import pytest
    from app.core.config import settings
    from app.agent.model import cloud_http
    from app.quality.sandbox import ModelBudget
    monkeypatch.setattr(settings, 'model_provider', 'cloud')
    sent = []
    monkeypatch.setattr(cloud_http, 'post', lambda *args, **kwargs: sent.append(True))
    budget = ModelBudget(1, 10)
    restore = budget.install()
    try:
        with pytest.raises(RuntimeError, match='预算已耗尽'):
            cloud_http.post('https://example.invalid/chat/completions', json={'messages': [{'content': '预算测试'}]})
        assert not sent
        assert budget.output()['exhausted'] is True
        assert budget.output()['max_tokens'] == 10
        assert budget.output()['calls'] == 0
    finally:
        restore()


def test_old_sqlite_is_replaced_only_inside_quality_runtime(monkeypatch):
    import sqlite3
    import sys
    from types import SimpleNamespace
    from app.quality.sandbox import ensure_sqlite
    modern = SimpleNamespace(sqlite_version_info=(3, 51, 0), dbapi2=object())
    monkeypatch.setattr(sqlite3, 'sqlite_version_info', (3, 31, 1))
    monkeypatch.setitem(sys.modules, 'sqlite3', sqlite3)
    monkeypatch.setitem(sys.modules, 'sqlite3.dbapi2', sqlite3.dbapi2)
    monkeypatch.setitem(sys.modules, 'pysqlite3', modern)
    ensure_sqlite()
    assert sys.modules['sqlite3'] is modern
    assert sys.modules['sqlite3.dbapi2'] is modern.dbapi2


def test_old_sqlite_missing_compatibility_library_is_explicitly_blocked(monkeypatch):
    import pytest
    import sqlite3
    import sys
    from app.quality.sandbox import ensure_sqlite
    monkeypatch.setattr(sqlite3, 'sqlite_version_info', (3, 31, 1))
    monkeypatch.setitem(sys.modules, 'pysqlite3', None)
    with pytest.raises(RuntimeError, match='pysqlite3-binary'):
        ensure_sqlite()
