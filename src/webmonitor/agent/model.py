"""SDK model transport, client networking and truncated-stream protection."""
import json

import httpx
from agents.exceptions import ModelBehaviorError
from agents.models.openai_chatcompletions import OpenAIChatCompletionsModel
from openai import AsyncOpenAI

from webmonitor.config import get_settings


async def create_model_client(*, max_retries: int) -> AsyncOpenAI:
    """Build the sole model client; only the explicit internal endpoint is direct."""
    settings = get_settings()
    internal = settings.container_runtime and bool(settings.openai_container_base_url)
    http_client = httpx.AsyncClient(
        proxy=None if internal else settings.egress_proxy_url,
        trust_env=False, timeout=settings.agent_model_timeout_seconds)
    try:
        return AsyncOpenAI(api_key=settings.openai_api_key.get_secret_value(),
            base_url=settings.model_base_url, timeout=settings.agent_model_timeout_seconds,
            max_retries=max_retries, http_client=http_client)
    except BaseException:
        await http_client.aclose()
        raise


class CompleteToolStream:
    """Preserve the provider stream interface while checking its actual terminal reason."""
    def __init__(self, stream):
        self.stream = stream

    def __getattr__(self, name):
        return getattr(self.stream, name)

    async def __aiter__(self):
        calls = {}
        finish = None
        async for chunk in self.stream:
            for choice in chunk.choices:
                if choice.index != 0:
                    raise ModelBehaviorError("Multiple completion choices are not supported")
                if choice.finish_reason is not None:
                    finish = choice.finish_reason
                for call in choice.delta.tool_calls or []:
                    if call.type not in {None, "function"}:
                        raise ModelBehaviorError("Unsupported tool call type")
                    record = calls.setdefault(call.index, {"id": "", "name": "", "arguments": ""})
                    if call.id:
                        record["id"] = call.id
                    if call.function:
                        if call.function.name:
                            record["name"] = call.function.name
                        record["arguments"] += call.function.arguments or ""
            if finish in {"length", "content_filter"}:
                raise ModelBehaviorError("Model response is incomplete")
            yield chunk
        if calls:
            if finish != "tool_calls":
                raise ModelBehaviorError("Tool response ended without successful completion")
            for record in calls.values():
                try:
                    arguments = json.loads(record["arguments"])
                except (ValueError, TypeError):
                    raise ModelBehaviorError("Tool arguments are incomplete") from None
                if not record["id"] or not record["name"] or not isinstance(arguments, dict):
                    raise ModelBehaviorError("Tool call is incomplete")
        elif finish != "stop":
            raise ModelBehaviorError("Model response ended without a terminal reason")

    async def close(self):
        await self.stream.close()


class CompleteChatCompletionsModel(OpenAIChatCompletionsModel):
    """Pinned SDK adapter, not a second model/tool loop."""
    async def _fetch_response(self, *args, **kwargs):
        result = await super()._fetch_response(*args, **kwargs)
        if isinstance(result, tuple):
            response, stream = result
            return response, CompleteToolStream(stream)
        return result
