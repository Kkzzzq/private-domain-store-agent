"""Independent test/judge model configuration, restricted to quality child processes."""
import os
import re


def configure_test_model():
    if not re.fullmatch(r'[a-f0-9]{32}',os.environ.get('QA_CHILD_RUN','')):
        raise RuntimeError('测试模型只能在受限质量子进程使用')
    from app.core.config import settings
    if not settings.qa_chat_model or not settings.qa_chat_api_key_file:
        raise RuntimeError('独立测试模型未配置，不能使用业务模型代替')
    settings.model_provider='cloud'
    settings.cloud_model=settings.qa_chat_model
    settings.cloud_base_url=settings.qa_chat_base_url
    settings.cloud_api_style=settings.qa_chat_api_style
    settings.cloud_api_key=''
    settings.cloud_api_key_file=settings.qa_chat_api_key_file
    settings.cloud_fallback_models=''
