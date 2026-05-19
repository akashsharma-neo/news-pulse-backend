"""
OpenRouter / OpenAI-compatible chat completion helpers.
"""

from django.conf import settings


def chat_web_search_enabled() -> bool:
    """Whether to attach OpenRouter web search server tools to chat requests."""
    return settings.CHAT_WEB_SEARCH_ENABLED


def build_chat_completion_kwargs(messages: list) -> dict:
    """
    Build kwargs for client.chat.completions.create().

    When web search is enabled (OpenRouter by default), attaches the
    openrouter:web_search server tool so the model can fetch current information.
    """
    kwargs = {
        "model": settings.OPENAI_COMPATIBLE_MODEL,
        "messages": messages,
        "max_tokens": settings.CHAT_MAX_TOKENS,
        "temperature": settings.CHAT_TEMPERATURE,
    }
    if chat_web_search_enabled():
        params = {"max_results": settings.CHAT_WEB_SEARCH_MAX_RESULTS}
        if settings.CHAT_WEB_SEARCH_MAX_TOTAL_RESULTS > 0:
            params["max_total_results"] = settings.CHAT_WEB_SEARCH_MAX_TOTAL_RESULTS
        kwargs["extra_body"] = {
            "tools": [
                {
                    "type": "openrouter:web_search",
                    "parameters": params,
                }
            ],
        }
    return kwargs
