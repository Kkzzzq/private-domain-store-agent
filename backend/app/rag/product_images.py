import base64
import ipaddress
import json
import math
import mimetypes
import socket
from hashlib import sha256
from pathlib import Path
from urllib.parse import unquote, urlsplit

import httpx
from filelock import FileLock

from app.core.config import settings
from app.core.credentials import embedding_api_key
from app.core.logging import logger
from app.rag.cloud_embeddings import EmbeddingQuotaError


def image_input(url):
    parsed = urlsplit(url)
    if parsed.scheme:
        if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password or parsed.port not in (None, 443):
            raise ValueError("图片必须是安全的公开HTTPS地址或本站图片")
        addresses = socket.getaddrinfo(parsed.hostname, 443, type=socket.SOCK_STREAM)
        if not addresses or any(not ipaddress.ip_address(address[4][0]).is_global for address in addresses):
            raise ValueError("不允许私网图片地址")
        return url, sha256(url.encode()).hexdigest()
    if parsed.netloc or parsed.query or parsed.fragment:
        raise ValueError("本站图片路径无效")
    root = settings.web_dir.resolve()
    relative = unquote(parsed.path).lstrip("/")
    if not relative.startswith(("covers/", "uploads/")):
        raise ValueError("只能读取本站商品图片")
    path = (root / relative).resolve()
    if not path.is_relative_to(root) or path.suffix.lower() not in {".jpg", ".jpeg", ".png", ".webp", ".gif"}:
        raise ValueError("图片路径或格式无效")
    if path.stat().st_size > 4 * 1024 * 1024:
        raise ValueError("图片超过4MB限制")
    data = path.read_bytes()
    valid = data.startswith((b"\xff\xd8\xff", b"\x89PNG\r\n\x1a\n", b"GIF87a", b"GIF89a")) or (data.startswith(b"RIFF") and data[8:12] == b"WEBP")
    if not valid:
        raise ValueError("文件不是支持的图片")
    mime = mimetypes.guess_type(str(path))[0] or "image/jpeg"
    return f"data:{mime};base64," + base64.b64encode(data).decode(), sha256(data).hexdigest()


def image_assets(rows):
    assets = []
    for row in rows:
        if row.get("image_url"):
            assets.append({"product_id": row["id"], "sku_id": 0, "image_url": row["image_url"], "inherited": False})
        for sku in row["skus"]:
            url = sku.get("image_url") or row.get("image_url")
            if url:
                assets.append({"product_id": row["id"], "sku_id": sku["id"], "image_url": url, "inherited": not bool(sku.get("image_url"))})
    return assets


class ImageEmbedder:
    def __init__(self, model, inputs):
        self.model_name = model
        self.input_version = "independent-image-v1"
        self.inputs = inputs

    def embed(self, item):
        response = httpx.post(settings.product_image_embedding_url,
                              headers={"Authorization": "Bearer " + embedding_api_key()},
                              json={"model": self.model_name, "input": {"contents": [item]}},
                              timeout=settings.cloud_timeout_seconds, follow_redirects=False)
        if not response.is_success:
            try:
                payload = response.json()
                code = str(payload.get("code") or payload.get("error", {}).get("code") or "")
            except ValueError:
                code = ""
            if code in {"AllocationQuota.FreeTierOnly", "QuotaExhausted", "QuotaExceeded", "InsufficientBalance"}:
                raise EmbeddingQuotaError("图像Embedding额度不可用")
            raise RuntimeError(f"图像Embedding请求失败HTTP{response.status_code}")
        rows = response.json().get("output", {}).get("embeddings", [])
        vector = rows[0].get("embedding") if len(rows) == 1 and isinstance(rows[0], dict) else None
        if not isinstance(vector, list) or not vector or any(type(value) not in (int, float) or not math.isfinite(value) for value in vector) or not any(vector):
            raise ValueError("图像Embedding返回无效向量")
        return vector

    def embed_documents(self, texts):
        cache, vectors = {}, []
        for text in texts:
            value = json.loads(text.split("\n", 1)[1])
            fingerprint = value["fingerprint"]
            if fingerprint not in cache:
                cache[fingerprint] = self.embed({"image": self.inputs[value["image_url"]]})
            vectors.append(cache[fingerprint])
        return vectors

    def embed_query(self, text):
        return self.embed({"text": text})


def search_product_images(question, rows, db, actor):
    from app.rag.knowledge import KnowledgeBase
    from app.rag.routing import cooling, mark_quota
    if not settings.product_image_embedding_enabled or settings.embedding_provider != "qwen":
        return set(), {"status": "disabled"}
    inputs, chunks, invalid = {}, [], []
    for asset in image_assets(rows):
        try:
            if asset["image_url"] not in inputs:
                inputs[asset["image_url"]] = image_input(asset["image_url"])
            _, fingerprint = inputs[asset["image_url"]]
            document = json.dumps({**asset, "fingerprint": fingerprint}, ensure_ascii=False)
            chunks.append({"id": f"p{asset['product_id']}-s{asset['sku_id']}", "source": str(asset["product_id"]),
                           "heading_path": str(asset["sku_id"]), "content": document})
        except (OSError, ValueError, socket.gaierror):
            invalid.append({"product_id": asset["product_id"], "sku_id": asset["sku_id"], "status": "unavailable"})
    scope = sha256((str(db.get_bind().url) + f":{actor.shop_id}:{actor.role}:images-v1").encode()).hexdigest()[:24]
    root = Path(settings.chroma_path) / "product-images" / scope
    root.mkdir(parents=True, exist_ok=True)
    models = list(dict.fromkeys([settings.product_image_embedding_model] + [value.strip() for value in settings.product_image_embedding_fallback_models.split(",") if value.strip()]))
    try:
        with FileLock(str(root / "index.lock"), timeout=30):
            for model in models[:5]:
                if cooling(model):
                    continue
                embedder = ImageEmbedder(model, {key: value[0] for key, value in inputs.items()})
                version = sha256((settings.product_image_embedding_url + model).encode()).hexdigest()[:24]
                base = KnowledgeBase(root, "images_" + version)
                try:
                    base.rebuild(chunks, embedder)
                    hits = base.semantic_search(question, embedder, k=12) if chunks and question else []
                except EmbeddingQuotaError:
                    mark_quota(model)
                    continue
                pairs = {(int(hit["source"]), int(hit["heading_path"])) for hit in hits}
                actor.embedding_model = model
                return pairs, {"status": "ready", "model": model, "indexed_assets": len(chunks), "unavailable_assets": invalid,
                               "matching_assets": [{"product_id": int(hit["source"]), "sku_id": int(hit["heading_path"]), "distance": hit["distance"]} for hit in hits]}
        raise RuntimeError("图像Embedding候选均不可用")
    except Exception as exc:
        logger.warning("图像Embedding暂不可用：%s", type(exc).__name__)
        return set(), {"status": "unavailable", "indexed_assets": 0, "unavailable_assets": invalid, "reason": type(exc).__name__}
