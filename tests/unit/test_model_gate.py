import pytest
from agents.exceptions import ModelBehaviorError
from agents.models.chatcmpl_stream_handler import ChatCmplStreamHandler
from openai.types.chat import ChatCompletionChunk

from webmonitor.agent.model import CompleteToolStream


async def provider(arguments, reason):
    yield ChatCompletionChunk.model_validate({"id":"completion","object":"chat.completion.chunk","created":1,"model":"model","choices":[{"index":0,"delta":{"tool_calls":[{"index":0,"id":"call1","type":"function","function":{"name":"create_monitor_task","arguments":arguments}}]},"finish_reason":None}]})
    if reason:
        yield ChatCompletionChunk.model_validate({"id":"completion","object":"chat.completion.chunk","created":1,"model":"model","choices":[{"index":0,"delta":{},"finish_reason":reason}]})


@pytest.mark.asyncio
@pytest.mark.parametrize("arguments,reason", [('{}','length'),('{}',None),('{"draft_id":','tool_calls'),('{}','content_filter'),('{}','stop')])
async def test_incomplete_stream_never_releases_tool_calls(arguments,reason):
    released=[]
    with pytest.raises(ModelBehaviorError):
        async for chunk in ChatCmplStreamHandler.buffer_tool_call_stream(CompleteToolStream(provider(arguments,reason))):
            released.extend(call for choice in chunk.choices for call in choice.delta.tool_calls or [])
    assert released==[]


@pytest.mark.asyncio
async def test_completed_tool_arguments_released_once():
    released=[]
    async for chunk in ChatCmplStreamHandler.buffer_tool_call_stream(CompleteToolStream(provider(arguments='{"draft_id":"approved"}',reason='tool_calls'))):
        released.extend(call for choice in chunk.choices for call in choice.delta.tool_calls or [])
    assert [(call.id,call.function.name,call.function.arguments) for call in released]==[('call1','create_monitor_task','{"draft_id":"approved"}')]


@pytest.mark.asyncio
@pytest.mark.parametrize("container,internal,expected_proxy", [
    (False, None, "http://egress:3128"),
    (True, None, "http://egress:3128"),
    (True, "http://model:8000/v1", None),
])
async def test_model_client_uses_proxy_except_for_explicit_internal_endpoint(
        monkeypatch, container, internal, expected_proxy):
    from webmonitor.agent import model
    from webmonitor.config import get_settings

    settings = get_settings()
    monkeypatch.setattr(settings, "container_runtime", container)
    monkeypatch.setattr(settings, "openai_container_base_url", internal)
    created = {}

    class FakeHTTP:
        def __init__(self, **kwargs):
            created["http"] = kwargs
            self.closed = False

        async def aclose(self):
            self.closed = True

    class FakeOpenAI:
        def __init__(self, **kwargs):
            created["openai"] = kwargs
            self.http = kwargs["http_client"]

        async def close(self):
            await self.http.aclose()

    monkeypatch.setattr(model.httpx, "AsyncClient", FakeHTTP)
    monkeypatch.setattr(model, "AsyncOpenAI", FakeOpenAI)
    client = await model.create_model_client(max_retries=7)
    assert created["http"]["proxy"] == expected_proxy
    assert created["http"]["trust_env"] is False
    assert created["openai"]["base_url"] == settings.model_base_url
    assert created["openai"]["max_retries"] == 7
    await client.close()
    assert client.http.closed


@pytest.mark.asyncio
async def test_model_client_constructor_failure_closes_http_resources(monkeypatch):
    from webmonitor.agent import model

    created = []

    class FakeHTTP:
        def __init__(self, **kwargs):
            self.closed = False
            created.append(self)

        async def aclose(self):
            self.closed = True

    class BrokenOpenAI:
        def __init__(self, **kwargs):
            raise RuntimeError("construction failed")

    monkeypatch.setattr(model.httpx, "AsyncClient", FakeHTTP)
    monkeypatch.setattr(model, "AsyncOpenAI", BrokenOpenAI)
    with pytest.raises(RuntimeError):
        await model.create_model_client(max_retries=0)
    assert created[0].closed
