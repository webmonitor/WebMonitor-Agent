"""A one-sentence template request becomes one validated, field-agnostic design."""
import json
from types import SimpleNamespace

import pytest

from webmonitor.agent.template_draft import draft_template
from webmonitor.errors import DomainError


def design(**overrides) -> dict:
    body = {
        "name": "Plain alert",
        "config": {
            "subject": "{monitor_name} · {event_label}",
            "style": {"accent": "#8a3123", "font": "serif", "density": "roomy",
                      "uppercase_labels": True},
            "intros": {"content_changed": "页面有变化。"},
            "blocks": [
                {"type": "summary"},
                {"type": "all_fields"},
                {"type": "evidence_link"},
            ],
        },
    }
    body.update(overrides)
    return body


class _Completions:
    def __init__(self, replies):
        self.replies = list(replies)
        self.calls: list[dict] = []

    async def create(self, **kwargs):
        self.calls.append(kwargs)
        reply = self.replies.pop(0)
        return SimpleNamespace(choices=[SimpleNamespace(
            message=SimpleNamespace(content=reply))])


class _Client:
    def __init__(self, replies):
        self.chat = SimpleNamespace(completions=_Completions(replies))


def text(reply) -> str:
    return reply if isinstance(reply, str) else json.dumps(reply)


@pytest.mark.asyncio
async def test_a_valid_reply_becomes_a_design():
    client = _Client([text(design())])
    proposal = await draft_template("  语气平实，列出全部内容  ", client=client, model="m")
    assert proposal.name == "Plain alert"
    assert proposal.config.subject == "{monitor_name} · {event_label}"
    assert proposal.config.style.accent == "#8a3123"
    assert proposal.config.style.font == "serif"
    assert [block.type for block in proposal.config.blocks] == [
        "summary", "all_fields", "evidence_link"]
    sent = client.chat.completions.calls[0]
    assert sent["model"] == "m"
    assert "语气平实，列出全部内容" in sent["messages"][0]["content"]
    assert "Never name a specific field" in sent["messages"][0]["content"]


@pytest.mark.asyncio
async def test_a_code_fence_and_prose_are_tolerated():
    client = _Client(["```json\n" + json.dumps(design()) + "\n```"])
    assert (await draft_template("x", client=client, model="m")).name == "Plain alert"


@pytest.mark.asyncio
async def test_an_invalid_reply_is_repaired_once_with_the_reason():
    bad = design(config={"subject": "", "blocks": []})
    client = _Client([text(bad), text(design())])
    proposal = await draft_template("x", client=client, model="m")
    assert proposal.name == "Plain alert"
    assert len(client.chat.completions.calls) == 2
    repair = client.chat.completions.calls[1]["messages"][-1]["content"]
    assert "invalid" in repair and "subject" in repair


@pytest.mark.asyncio
async def test_a_named_field_block_is_rejected_and_asked_again():
    named = design(config={
        "subject": "{monitor_name}",
        "blocks": [{"type": "field", "field": "page_title"}],
    })
    client = _Client([text(named), text(design())])
    proposal = await draft_template("x", client=client, model="m")
    assert [block.type for block in proposal.config.blocks][0] == "summary"
    assert "field" in client.chat.completions.calls[1]["messages"][-1]["content"]


@pytest.mark.asyncio
async def test_two_invalid_replies_fail_with_the_reasons():
    bad = design(config={"subject": "x", "blocks": [{"type": "field", "field": "fee"}]})
    client = _Client([text(bad), text(bad)])
    with pytest.raises(DomainError) as raised:
        await draft_template("x", client=client, model="m")
    assert raised.value.code == "template_generation_failed"
    assert raised.value.status == 502
    assert raised.value.details["errors"]
    assert len(client.chat.completions.calls) == 2


@pytest.mark.asyncio
async def test_an_unreadable_palette_is_sent_back_once():
    washed = design(config={
        "subject": "{monitor_name}",
        "style": {"text": "#f0f0f0", "surface": "#ffffff"},
        "blocks": [{"type": "summary"}],
    })
    client = _Client([text(washed), text(design())])
    proposal = await draft_template("x", client=client, model="m")
    assert proposal.config.style.text != "#f0f0f0"
    assert "contrast" in client.chat.completions.calls[1]["messages"][-1]["content"]


@pytest.mark.asyncio
async def test_a_non_json_reply_is_not_a_design():
    client = _Client(["I cannot do that.", "{}"])
    with pytest.raises(DomainError) as raised:
        await draft_template("x", client=client, model="m")
    assert raised.value.code == "template_generation_failed"


@pytest.mark.asyncio
async def test_a_blank_request_is_refused_before_the_model():
    client = _Client([text(design())])
    with pytest.raises(DomainError) as raised:
        await draft_template("   ", client=client, model="m")
    assert raised.value.code == "validation_failed"
    assert client.chat.completions.calls == []
