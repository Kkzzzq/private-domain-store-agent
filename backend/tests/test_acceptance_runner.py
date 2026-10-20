import hashlib
import io
import json
from types import SimpleNamespace

import pytest

from scripts import pull_ollama_model
from scripts.live_acceptance import Acceptance


def test_incomplete_live_report_cannot_pass(tmp_path):
    suite = Acceptance.__new__(Acceptance)
    suite.args = SimpleNamespace(phase="full", report=str(tmp_path / "report.json"))
    suite.report = {"cases": [{"name": "one", "status": "passed"}]}
    suite.save()
    report = json.loads((tmp_path / "report.json").read_text(encoding="utf-8"))
    assert not report["passed"] and report["expected_cases"] == 7


@pytest.mark.parametrize("target", ["http://registry.ollama.ai/file", "https://localhost/file", "https://example.test/file"])
def test_model_download_redirect_restricts_source(target):
    with pytest.raises(ValueError, match="官方HTTPS"):
        pull_ollama_model.PublicRegistryRedirect().redirect_request(None, None, 302, "", {}, target)


def test_model_download_rejects_fake_ip(monkeypatch):
    monkeypatch.setattr(pull_ollama_model.socket, "getaddrinfo", lambda *args, **kwargs: [(2, 1, 6, "", ("198.18.0.1", 443))])
    with pytest.raises(ValueError, match="公网地址"):
        pull_ollama_model.PublicRegistryRedirect().redirect_request(None, None, 302, "", {}, "https://test.r2.cloudflarestorage.com/file")


@pytest.mark.parametrize("corrupt", [False, True])
def test_model_download_checks_size_and_digest_before_publish(tmp_path, monkeypatch, corrupt):
    payload = b"verified-test-weights"
    checksum = hashlib.sha256(payload).hexdigest()
    descriptor = {"digest": "sha256:" + checksum, "size": len(payload)}
    manifest = json.dumps({"config": descriptor, "layers": []}).encode()
    class Response(io.BytesIO):
        status = 200
    class Opener:
        def open(self, request, timeout):
            if "/manifests/" in request.full_url:
                return Response(manifest)
            return Response(b"wrong-model-weights!!" if corrupt else payload)
    monkeypatch.setattr(pull_ollama_model, "build_opener", lambda *args: Opener())
    monkeypatch.setattr(pull_ollama_model.time, "sleep", lambda duration: None)
    monkeypatch.setattr("sys.argv", ["pull", "example:latest", "--root", str(tmp_path)])
    published = tmp_path / "manifests/registry.ollama.ai/library/example/latest"
    if corrupt:
        with pytest.raises(RuntimeError, match="下载失败"):
            pull_ollama_model.main()
        assert not published.exists()
    else:
        pull_ollama_model.main()
        assert published.exists()
        assert (tmp_path / "blobs" / ("sha256-" + checksum)).read_bytes() == payload
