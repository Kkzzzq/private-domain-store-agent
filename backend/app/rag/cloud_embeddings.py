import math
import time

import httpx

from app.core.config import settings
from app.core.credentials import cloud_api_key


class ZhipuEmbedder:
    def __init__(self):
        if settings.cloud_api_style != "zhipu" or not settings.cloud_base_url:
            raise RuntimeError("智谱Embedding需要明确的智谱API配置")
        self.model_name = settings.cloud_embedding_model
        self.dimensions = settings.cloud_embedding_dimensions
        self.input_version = f"zhipu-heading-v1-d{self.dimensions}"

    def embed_documents(self, texts):
        if any(not isinstance(text, str) or not text.strip() or len(text) > 6000 for text in texts):
            raise ValueError("Embedding输入为空、过长或格式无效")
        vectors = []
        for offset in range(0, len(texts), 64):
            batch = texts[offset:offset + 64]
            for attempt in range(3):
                response = httpx.post(settings.cloud_base_url.rstrip("/") + "/embeddings",
                                      headers={"Authorization": "Bearer " + cloud_api_key()},
                                      json={"model": self.model_name, "input": batch, "dimensions": self.dimensions},
                                      timeout=settings.cloud_timeout_seconds)
                if response.status_code not in (429, 503) or attempt == 2:
                    break
                time.sleep(2 ** attempt)
            if not response.is_success:
                raise RuntimeError(f"Embedding调用失败 HTTP {response.status_code}")
            payload = response.json()
            data = payload.get("data") if isinstance(payload, dict) else None
            if not isinstance(data, list) or len(data) != len(batch):
                raise ValueError("Embedding返回数量不匹配")
            if any(not isinstance(row, dict) or type(row.get("index")) is not int for row in data):
                raise ValueError("Embedding返回索引无效")
            data.sort(key=lambda row: row["index"])
            if [row["index"] for row in data] != list(range(len(batch))):
                raise ValueError("Embedding返回索引不完整或重复")
            for row in data:
                vector = row.get("embedding")
                if not isinstance(vector, list) or len(vector) != self.dimensions:
                    raise ValueError("Embedding返回维度不匹配")
                if any(type(value) not in (int, float) or not math.isfinite(value) for value in vector) or not any(vector):
                    raise ValueError("Embedding返回非有限值或零向量")
                vectors.append(vector)
        return vectors

    def embed_query(self, text):
        return self.embed_documents([text])[0]
