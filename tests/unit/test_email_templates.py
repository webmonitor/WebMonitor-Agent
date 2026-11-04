"""Structured templates render data, never code; packaged mail keeps working."""
import pytest

from webmonitor.errors import DomainError
from webmonitor.notifications.custom import preview_template, render_custom_email, sample_payload
from webmonitor.notifications.rendering import render_email
from webmonitor.schemas.monitors import MonitorSpec
from webmonitor.schemas.notifications import EVENT_TYPES
from webmonitor.schemas.templates import (
    EmailTemplateConfig,
    TemplateIncompatible,
    template_fields,
    validate_template_for_spec,
)

SPEC = MonitorSpec.model_validate({
    "name": "Notice watch", "url": "https://example.com/notice", "collection_mode": "http",
    "fields": [
        {"name": "page_title", "type": "text", "semantic": "Page title", "selector": "h1"},
        {"name": "notice", "type": "list", "semantic": "Notices", "selector": "li",
         "item_fields": [
             {"name": "title", "type": "text", "semantic": "Title", "selector": ".t"},
             {"name": "state", "type": "text", "semantic": "State", "selector": ".s"}]},
    ],
    "business_key": {"field": "notice", "item_fields": ["title"]},
    "change_rules": {"mode": "any", "rules": [
        {"type": "list_updated", "field": "notice", "watch_fields": ["state"]},
        {"type": "text_changed", "field": "page_title"}]},
    "coverage": {"scope": "full", "description": "Whole notice list"},
})


def config(**overrides) -> EmailTemplateConfig:
    body = {
        "subject": "{monitor_name} 的 {event_label}",
        "style": {"accent": "#8a3123", "font": "serif", "density": "roomy"},
        "blocks": [
            {"type": "text", "text": "第一段"},
            {"type": "summary"},
            {"type": "field", "field": "page_title", "show": "both", "emphasis": True,
             "label": "当前标题"},
            {"type": "list_changes", "field": "notice", "limit": 1},
            {"type": "event_time"},
            {"type": "monitor_link"},
            {"type": "evidence_link"},
            {"type": "divider"},
        ],
    }
    body.update(overrides)
    return EmailTemplateConfig.model_validate(body)


def changed_payload(event_type: str = "content_changed") -> dict:
    payload = sample_payload()
    return {**payload, "event": {**payload["event"], "type": event_type}}


def test_blocks_render_in_the_stored_order():
    html = render_custom_email("content_changed", changed_payload(), config())["html"]
    first = html.index("第一段")
    title = html.index("当前标题")
    rows = html.index("公告列表")
    clock = html.index("检测时间")
    page = html.index("监控页面")
    evidence = html.index("查看完整记录")
    assert first < title < rows < clock < page < evidence < html.index("<hr")
    text = render_custom_email("content_changed", changed_payload(), config())["text"]
    assert text.index("第一段") < text.index("当前标题") < text.index("公告列表")
    assert text.index("检测时间") < text.index("监控页面") < text.index("查看完整记录")


def test_values_are_escaped_and_tokens_are_substituted():
    payload = sample_payload()
    payload["fields"]["page_title"] = '<script>alert("x")</script>'
    payload["monitor"]["name"] = "A&B <Notice>"
    design = config(subject="{monitor_name} · {event_date} · {event_label}",
                    blocks=[{"type": "all_fields", "fields": ["page_title"]}])
    message = render_custom_email("content_changed", payload, design)
    assert "<script>" not in message["html"]
    assert "&lt;script&gt;" in message["html"]
    assert "A&B <Notice>" not in message["html"]
    assert "A&amp;B &lt;Notice&gt;" in message["html"]
    assert message["subject"].startswith("A&B <Notice> · 2024-05-06 02:30 UTC · ")
    assert message["subject"].endswith("内容变化")


def test_subject_never_breaks_into_a_new_header_line():
    payload = sample_payload()
    payload["monitor"]["name"] = "Name\r\nBcc: victim@example.com"
    message = render_custom_email("content_changed", payload, config(subject="{monitor_name}"))
    assert "\r" not in message["subject"] and "\n" not in message["subject"]


def test_a_field_absent_from_the_event_renders_an_em_dash():
    design = config(blocks=[{"type": "field", "field": "page_title", "show": "before"}])
    payload = sample_payload()
    payload["change"]["before"] = None
    message = render_custom_email("content_changed", payload, design)
    assert "—" in message["text"]
    assert "—" in message["html"]


def test_list_rows_are_capped_and_counted():
    design = config(blocks=[{"type": "list_changes", "field": "notice", "limit": 1}])
    payload = sample_payload()
    payload["change"]["differences"] = [{
        "type": "list_added", "field": "notice",
        "items": [{"title": f"Notice {index}", "state": "Open"} for index in range(3)]}]
    message = render_custom_email("list_changed", payload, design)
    assert "Notice 0" in message["text"] and "Notice 1" not in message["text"]
    assert "另有 2 项" in message["text"] and "另有 2 项" in message["html"]


def test_evidence_link_is_omitted_when_absent():
    design = config(blocks=[{"type": "evidence_link"}])
    payload = {**sample_payload(), "evidence_url": ""}
    message = render_custom_email("content_changed", payload, design)
    assert "查看完整记录" not in message["html"]
    assert "查看完整记录" not in message["text"]


def test_style_tokens_are_the_whole_look():
    message = render_custom_email("recovered", sample_payload(), config())
    html = message["html"]
    assert html.startswith("<!doctype html>")
    assert "max-width:620px" in html
    assert "#8a3123" in html            # accent reaches links and values
    assert "Georgia" in html            # font family token
    assert "padding:40px" in html       # roomy density
    assert "<script" not in html


def test_preview_keeps_the_designs_own_paper_and_type():
    from webmonitor.notifications.rendering import sanitize_preview

    dark = EmailTemplateConfig.model_validate({
        "subject": "{monitor_name}",
        "style": {"page_background": "#0d1117", "text": "#e6edf3", "font": "mono",
                  "density": "tight"},
        "blocks": [{"type": "summary"}]})
    clean = sanitize_preview(render_custom_email("content_changed", sample_payload(), dark)["html"])
    assert "background:#0d1117" in clean
    assert "ui-monospace" in clean
    # Packaged mail keeps its own paper.
    packaged = sanitize_preview(render_email("content_changed", sample_payload())["html"])
    assert "#f5f2ea" in packaged


def test_a_light_design_stays_one_shell():
    plain = EmailTemplateConfig.model_validate({
        "subject": "{monitor_name}",
        "style": {"page_background": "#ffffff", "surface": "#ffffff", "border": False,
                  "radius": 0, "density": "tight", "uppercase_labels": True},
        "blocks": [{"type": "summary"}]})
    html = render_custom_email("content_changed", sample_payload(), plain)["html"]
    assert "border:0" in html and "border-radius:0" in html
    assert "text-transform:uppercase" in html
    assert "padding:12px" in html


def test_intro_is_per_event_and_optional():
    design = config(intros={"content_changed": "页面内容发生变化"})
    assert "页面内容发生变化" in render_custom_email(
        "content_changed", changed_payload(), design)["text"]
    assert "页面内容发生变化" not in render_custom_email(
        "run_failed", changed_payload("run_failed"), design)["text"]


def test_template_preview_renders_every_event_type():
    rendered = preview_template(config())
    assert [item["event_type"] for item in rendered] == sorted(EVENT_TYPES)
    assert all(item["preview_html"].startswith("<!doctype html>") for item in rendered)
    assert all("<script" not in item["html"] for item in rendered)


def test_unknown_fields_are_rejected_against_a_spec():
    design = config(blocks=[{"type": "field", "field": "last_page"}])
    with pytest.raises(TemplateIncompatible) as raised:
        validate_template_for_spec(design, SPEC)
    assert raised.value.fields == ["last_page"]
    assert "last_page" in str(raised.value)


def test_list_changes_must_use_the_business_key_list():
    other = EmailTemplateConfig.model_validate({
        "subject": "{monitor_name}",
        "blocks": [{"type": "list_changes", "field": "page_title"}]})
    with pytest.raises(TemplateIncompatible) as raised:
        validate_template_for_spec(other, SPEC)
    assert raised.value.fields == ["page_title"]
    validate_template_for_spec(config(), SPEC)


def test_template_fields_lists_every_read_field():
    design = config(blocks=[{"type": "field", "field": "page_title"},
                            {"type": "all_fields", "fields": ["notice"]},
                            {"type": "all_fields"}])
    assert template_fields(design) == ["page_title", "notice"]


@pytest.mark.parametrize("event_type", sorted(EVENT_TYPES))
def test_packaged_templates_still_render_every_event_type(event_type):
    payload = sample_payload()
    payload["event"]["type"] = event_type
    message = render_email(event_type, payload)
    assert message["subject"].startswith(payload["monitor"]["name"])
    assert "WebMonitor" in message["html"] and "WebMonitor" in message["text"]


def test_packaged_mail_needs_no_named_field():
    """Any field name renders: the packaged templates read the payload, not a convention."""
    payload = sample_payload()
    fields = {"fee": {"amount": "100.00", "currency": "CNY"},
              "deadline": "2024-09-20T00:00:00+00:00"}
    before = {"fee": {"amount": "90.00", "currency": "CNY"},
              "deadline": "2024-09-13T00:00:00+00:00"}
    payload["fields"] = fields
    payload["change"] = {**payload["change"], "after": fields, "before": before,
                        "differences": [
                            {"type": "threshold", "field": "fee",
                             "before": before["fee"], "after": fields["fee"]},
                            {"type": "text_changed", "field": "deadline",
                             "before": before["deadline"], "after": fields["deadline"]}]}
    payload["event"]["type"] = "content_changed"
    message = render_email("content_changed", payload)
    assert "CNY 100.00" in message["text"] and "CNY 90.00" in message["text"]
    assert "2024-09-20" in message["text"]


def test_unknown_event_type_is_rejected():
    with pytest.raises(DomainError) as raised:
        render_email("something_else", sample_payload())
    assert raised.value.code == "template_unavailable"
