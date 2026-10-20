from pathlib import Path

from app.core.config import settings


def cloud_api_key():
    key = settings.cloud_api_key
    if not key and settings.cloud_api_key_file:
        try:
            key = Path(settings.cloud_api_key_file).read_text(encoding="utf-8-sig").strip()
        except (OSError, UnicodeError):
            raise RuntimeError("云端模型密钥文件无法读取") from None
        if not key or any(character.isspace() for character in key):
            raise RuntimeError("云端模型密钥文件格式无效")
    if not key:
        raise RuntimeError("云端模型未配置")
    return key


def embedding_api_key():
    key = settings.cloud_embedding_api_key
    if not key and settings.cloud_embedding_api_key_file:
        try:
            key = Path(settings.cloud_embedding_api_key_file).read_text(encoding="utf-8-sig").strip()
        except (OSError, UnicodeError):
            raise RuntimeError("向量模型密钥文件无法读取") from None
        if not key or any(character.isspace() for character in key):
            raise RuntimeError("向量模型密钥文件格式无效")
    if key:
        return key
    if settings.cloud_embedding_base_url:
        raise RuntimeError("独立向量端点必须配置独立密钥，不能隐式复用聊天密钥")
    return cloud_api_key()
