import os
from typing import Optional

from langchain_openai import ChatOpenAI


def _is_valid_api_key(key: Optional[str]) -> bool:
    try:
        from app.utils.api_key_utils import is_valid_api_key

        return is_valid_api_key(key)
    except Exception:
        if not key or len(key) <= 10:
            return False
        if key.startswith("your_") or key.startswith("your-"):
            return False
        if key.endswith("_here") or key.endswith("-here"):
            return False
        if "..." in key:
            return False
        return True


class ChatXiaomiOpenAI(ChatOpenAI):
    def __init__(
        self,
        model: str,
        api_key: Optional[str] = None,
        base_url: str = "https://api.xiaomimimo.com/v1",
        temperature: float = 0.1,
        max_tokens: Optional[int] = None,
        timeout: Optional[int] = None,
        **kwargs,
    ):
        if api_key is None:
            env_api_key = os.getenv("MIMO_API_KEY")
            if env_api_key and _is_valid_api_key(env_api_key):
                api_key = env_api_key

        if not api_key:
            raise ValueError(
                "小米大模型 API 密钥未找到。请在 Web 界面配置 API Key "
                "(设置 -> 大模型厂家) 或设置 XIAOMI_API_KEY 环境变量。"
            )

        init_kwargs = {
            "model": model,
            "api_key": api_key,
            "base_url": base_url,
            "temperature": temperature,
            "max_tokens": max_tokens,
            **kwargs,
        }
        if timeout is not None:
            init_kwargs["timeout"] = timeout

        super().__init__(**init_kwargs)
