import os
from typing import Any, Dict, Optional

from langchain_openai import ChatOpenAI

from ..config.config_manager import token_tracker
from tradingagents.utils.logging_manager import get_logger

logger = get_logger("agents")


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


class ChatMimoOpenAI(ChatOpenAI):
    def __init__(self, **kwargs: Any):
        logger.info("开始初始化 ChatMimoOpenAI")

        api_key_from_kwargs = kwargs.get("api_key")
        if not api_key_from_kwargs:
            env_api_key = os.getenv("MIMO_API_KEY") or os.getenv("XIAOMI_API_KEY")
            if env_api_key and _is_valid_api_key(env_api_key):
                api_key_from_kwargs = env_api_key
            else:
                api_key_from_kwargs = None

        base_url = kwargs.get("base_url")
        if not base_url:
            kwargs["base_url"] = "https://api.xiaomimimo.com/v1"

        kwargs["api_key"] = api_key_from_kwargs
        kwargs.setdefault("model", "mimo-v2-flash")
        kwargs.setdefault("temperature", 0.1)
        kwargs.setdefault("max_tokens", 2000)

        if not kwargs.get("api_key"):
            raise ValueError(
                "小米大模型 API 密钥未找到。请在 Web 界面配置 API Key "
                "(设置 -> 大模型厂家) 或设置 MIMO_API_KEY 环境变量。"
            )

        super().__init__(**kwargs)
        logger.info("ChatMimoOpenAI 初始化成功")

    def _generate(self, *args: Any, **kwargs: Any):
        result = super()._generate(*args, **kwargs)

        try:
            if hasattr(result, "llm_output") and result.llm_output:
                token_usage = result.llm_output.get("token_usage", {})
                input_tokens = token_usage.get("prompt_tokens", 0)
                output_tokens = token_usage.get("completion_tokens", 0)

                if input_tokens > 0 or output_tokens > 0:
                    session_id = kwargs.get(
                        "session_id", f"mimo_openai_{hash(str(args)) % 10000}"
                    )
                    analysis_type = kwargs.get("analysis_type", "stock_analysis")
                    token_tracker.track_usage(
                        provider="mimo",
                        model_name=self.model_name,
                        input_tokens=input_tokens,
                        output_tokens=output_tokens,
                        session_id=session_id,
                        analysis_type=analysis_type,
                    )
        except Exception as track_error:
            logger.error(f"Token 追踪失败: {track_error}")

        return result

MIMO_OPENAI_MODELS: Dict[str, Dict[str, Any]] = {
    "mimo-v2-flash": {
        "description": "小米大模型 Mimo V2 Flash",
        "context_length": 8192,
        "supports_function_calling": True,
        "recommended_for": ["快速任务", "日常对话", "简单分析"],
    }
}


def get_available_openai_models() -> Dict[str, Dict[str, Any]]:
    return MIMO_OPENAI_MODELS


def create_mimo_openai_llm(
    model: str = "mimo-v2-flash",
    api_key: Optional[str] = None,
    temperature: float = 0.1,
    max_tokens: int = 2000,
    base_url: Optional[str] = None,
    **kwargs: Any,
) -> ChatMimoOpenAI:
    init_kwargs: Dict[str, Any] = dict(
        model=model,
        api_key=api_key,
        temperature=temperature,
        max_tokens=max_tokens,
        **kwargs,
    )
    if base_url:
        init_kwargs["base_url"] = base_url
    return ChatMimoOpenAI(**init_kwargs)


def test_mimo_openai_connection(
    model: str = "mimo-v2-flash", api_key: Optional[str] = None
) -> bool:
    try:
        llm = create_mimo_openai_llm(model=model, api_key=api_key, max_tokens=64)
        response = llm.invoke("你好，请用一句话介绍你自己。")
        return bool(response and getattr(response, "content", None))
    except Exception as e:
        logger.error(f"Mimo OpenAI 兼容接口连接测试失败: {e}")
        return False


def test_mimo_openai_function_calling(
    model: str = "mimo-v2-flash", api_key: Optional[str] = None
) -> bool:
    try:
        from langchain_core.tools import tool

        @tool
        def test_tool(query: str) -> str:
            return f"收到查询: {query}"

        llm = create_mimo_openai_llm(model=model, api_key=api_key, max_tokens=200)
        llm_with_tools = llm.bind_tools([test_tool])
        response = llm_with_tools.invoke("请使用test_tool查询'hello world'")
        if hasattr(response, "tool_calls") and response.tool_calls:
            return True
        return bool(response and getattr(response, "content", None) is not None)
    except Exception as e:
        logger.error(f"Mimo OpenAI Function Calling 测试失败: {e}")
        return False


if __name__ == "__main__":
    ok = test_mimo_openai_connection()
    if ok:
        ok = test_mimo_openai_function_calling()
    raise SystemExit(0 if ok else 1)
