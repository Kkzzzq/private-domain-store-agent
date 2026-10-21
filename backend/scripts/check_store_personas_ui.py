import json
import os
from pathlib import Path
import shutil
import socket
import subprocess
import sys
import tempfile
import time
from uuid import uuid4

import httpx
from playwright.sync_api import expect, sync_playwright


def main():
    backend = Path(__file__).resolve().parents[1]
    artifacts = backend / "data/acceptance"
    artifacts.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="persona-ui-", dir=artifacts) as folder:
        workspace = Path(folder)
        shutil.copytree(backend.parent / "web", workspace / "web", ignore=shutil.ignore_patterns("uploads", "node_modules"))
        with socket.socket() as connection:
            connection.bind(("127.0.0.1", 0))
            port = connection.getsockname()[1]
        origin = f"http://127.0.0.1:{port}"
        environment = dict(os.environ, DATABASE_URL="sqlite:///" + (workspace / "db.sqlite").as_posix(),
                           REDIS_URL="memory", STRICT_DEPENDENCIES="false", AGENT_MODE="fallback", MODEL_PROVIDER="ollama",
                           EMBEDDING_PROVIDER="ollama", RAG_REQUIRE_VECTORS="false", QA_REAL_SHOP_ENABLED="false",
                           JWT_SECRET=uuid4().hex + uuid4().hex, QA_CHILD_RUN=uuid4().hex,
                           QA_CHILD_WORKSPACE=folder, CHROMA_PATH=str(workspace / "chroma"))
        process = subprocess.Popen([sys.executable, "-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", str(port)],
                                   cwd=backend, env=environment, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        try:
            for _ in range(80):
                try:
                    if httpx.get(origin + "/api/v1/health").status_code == 200:
                        break
                except httpx.HTTPError:
                    pass
                time.sleep(.25)
            results = []
            with sync_playwright() as playwright:
                browser = playwright.chromium.launch(channel="msedge", headless=True)
                for role, username in (("merchant", "merchant"), ("customer", "alice")):
                    login = httpx.post(origin + "/api/v1/auth/login", json={"username": username, "password": username + "123"})
                    login.raise_for_status()
                    context = browser.new_context(viewport={"width": 1440, "height": 1050})
                    page = context.new_page()
                    errors = []
                    page.on("pageerror", lambda error: errors.append(str(error)))
                    key = "token_b" if role == "merchant" else "token_c"
                    page.add_init_script(f"sessionStorage.setItem({json.dumps(key)}, {json.dumps(login.json()['access_token'])});")
                    answer = "这是运营建议。" if role == "merchant" else "我可以帮您选购。"
                    data = {"session_id": "synthetic-ui", "answer": answer, "mode": "llm", "tools": [],
                            "notices": ["INTERNAL_NOTICE_DO_NOT_SHOW"], "intent": "unclear", "products": [],
                            "sources": [{"source": "INTERNAL_SOURCE_DO_NOT_SHOW.md", "heading_path": "internal"}], "retrieval_mode": "chroma"}
                    body = json.dumps({"type": "result", "data": data}, ensure_ascii=False) + "\n"
                    page.route("**/chat/stream", lambda route: route.fulfill(status=200, content_type="application/x-ndjson", body=body))
                    page.goto(origin + ("/b.html" if role == "merchant" else "/c.html?code=nanzhi"))
                    if role == "merchant":
                        page.locator(".merchant-chat-fab").click()
                        field = page.get_by_placeholder("例如：配置商品 / 经营概览 / 库存预警")
                    else:
                        page.get_by_role("button", name="打开购物小助手", exact=True).click()
                        field = page.get_by_placeholder("输入问题…")
                    send = page.get_by_role("button", name="发送", exact=True)
                    expect(send).to_be_enabled()
                    field.fill("优惠券如何配置" if role == "merchant" else "想买杯子")
                    send.click()
                    expect(page.get_by_text(answer, exact=True)).to_be_visible()
                    expect(page.get_by_text("运营小助手" if role == "merchant" else "购物小助手", exact=False)).to_be_visible()
                    text = page.locator("body").inner_text()
                    assert "INTERNAL_SOURCE_DO_NOT_SHOW" not in text and "INTERNAL_NOTICE_DO_NOT_SHOW" not in text
                    assert not errors, errors
                    page.screenshot(path=str(artifacts / f"persona-{role}-ui.png"), full_page=True)
                    results.append({"role": role, "status": "passed", "scope": "isolated-mocked-response-ui-not-model-evaluation", "errors": errors})
                    context.close()
                browser.close()
            (artifacts / "store-personas-ui.json").write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
            print(json.dumps(results, ensure_ascii=False))
        finally:
            process.terminate()
            process.wait(timeout=15)


if __name__ == "__main__":
    main()
