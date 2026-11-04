"""Request contracts reject ambiguous input before any service call."""
from uuid import uuid4

import pytest
from pydantic import ValidationError

from webmonitor.schemas.api import (
    ApproveRequest,
    DraftUpdate,
    EmailTemplatePatch,
    EmailTemplateSpec,
    GroupPatch,
    GroupSpec,
    MonitorRename,
    PostMessageRequest,
)
from webmonitor.schemas.delivery import DeliverySettings
from webmonitor.schemas.monitors import MonitorSpec
from webmonitor.schemas.templates import EmailTemplateConfig

SPEC = {
    "name": "Price watch", "url": "https://8.8.8.8/product", "collection_mode": "http",
    "fields": [{"name": "current_price", "type": "money", "semantic": "Price",
                "selector": ".price",
                "normalize": {"decimal_separator": ".", "currency": "USD"}}],
    "change_rules": {"mode": "any", "rules": [
        {"type": "number_percent_change", "field": "current_price",
         "operator": "decrease_gte", "value": 10}]},
    "coverage": {"scope": "full", "description": "Single price element"},
}


def test_message_requires_content_and_a_client_id():
    with pytest.raises(ValidationError):
        PostMessageRequest(content="", client_message_id="abc")
    with pytest.raises(ValidationError):
        PostMessageRequest(content="hello")
    with pytest.raises(ValidationError):
        PostMessageRequest(content="hello", client_message_id="x" * 65)
    assert PostMessageRequest(content="hello", client_message_id="abc").content == "hello"


def test_approval_requires_both_previews_and_revisions():
    complete = {"draft_id": uuid4(), "spec_revision": 3, "settings_revision": 2,
                "extraction_preview_hash": "a" * 64, "delivery_preview_hash": "b" * 64}
    approval = ApproveRequest(**complete)
    assert (approval.spec_revision, approval.settings_revision) == (3, 2)
    for missing in ("settings_revision", "spec_revision", "extraction_preview_hash",
                    "delivery_preview_hash", "draft_id"):
        body = {key: value for key, value in complete.items() if key != missing}
        with pytest.raises(ValidationError):
            ApproveRequest(**body)
    with pytest.raises(ValidationError):
        ApproveRequest(**{**complete, "extraction_preview_hash": "not-a-hash"})
    with pytest.raises(ValidationError):
        ApproveRequest(**{**complete, "delivery_preview_hash": "b" * 63})
    with pytest.raises(ValidationError):
        ApproveRequest(**complete, preview_id=str(uuid4()))


def test_group_members_are_unique_and_normalized():
    group = GroupSpec(name="Ops", members=[{"email": " Ops@Example.com "}, {"email": "two@example.com"}])
    assert [str(member.email) for member in group.members] == ["ops@example.com", "two@example.com"]
    with pytest.raises(ValidationError):
        GroupSpec(name="Ops", members=[{"email": "a@example.com"}, {"email": "A@example.com"}])
    with pytest.raises(ValidationError):
        GroupSpec(name="", members=[])


def test_group_patch_is_partial():
    patch = GroupPatch(enabled=False)
    assert patch.enabled is False
    assert patch.name is None and patch.members is None


def test_direct_edit_carries_one_section_and_its_revision():
    spec = MonitorSpec.model_validate(SPEC).model_dump(mode="json")
    assert DraftUpdate(spec_revision=1, spec=spec).spec_revision == 1
    settings = DeliverySettings.model_validate({"schedule": {
        "interval_seconds": 60, "timezone": "UTC"}})
    assert DraftUpdate(settings_revision=2, settings=settings).settings_revision == 2
    assert DraftUpdate(spec_revision=1, spec=spec, settings_revision=2,
                       settings=settings).settings is not None
    with pytest.raises(ValidationError):
        DraftUpdate(spec_revision=1, spec=spec, preview_id=str(uuid4()))
    with pytest.raises(ValidationError):
        DraftUpdate(spec=spec)
    with pytest.raises(ValidationError):
        DraftUpdate(settings=settings)
    with pytest.raises(ValidationError):
        DraftUpdate(spec_revision=1, settings_revision=1)
    with pytest.raises(ValidationError):
        DraftUpdate(spec_revision=1, spec={**spec, "fields": []})
    with pytest.raises(ValidationError):
        DraftUpdate(spec_revision=1, spec={**spec, "notification_group_ids": [str(uuid4())]})
    with pytest.raises(ValidationError):
        DraftUpdate(spec_revision="1", spec=spec)
    with pytest.raises(ValidationError):
        DraftUpdate()


def test_delivery_settings_validate_groups_and_the_interval():
    group_id = uuid4()
    settings = DeliverySettings.model_validate({"notification_group_ids": [str(group_id)],
        "schedule": {"interval_seconds": 60, "timezone": "Asia/Shanghai"}})
    assert settings.notification_group_ids == [group_id]
    assert settings.email_template_id is None
    assert DeliverySettings.model_validate({}).notification_group_ids == []
    with pytest.raises(ValidationError):
        DeliverySettings.model_validate({"notification_group_ids": [group_id, group_id]})
    with pytest.raises(ValidationError):
        DeliverySettings.model_validate({"schedule": {"interval_seconds": 5,
                                                      "timezone": "UTC"}})
    with pytest.raises(ValidationError):
        DeliverySettings.model_validate({"schedule": {"interval_seconds": 60,
                                                      "timezone": "Mars/Base"}})
    with pytest.raises(ValidationError):
        DeliverySettings.model_validate({"email_template_id": "not-a-uuid"})


def test_subject_tokens_are_allowlisted():
    def build(subject: str) -> EmailTemplateConfig:
        return EmailTemplateConfig.model_validate({"subject": subject})

    assert build(" {monitor_name} · {event_label} · {event_date} ").subject == (
        "{monitor_name} · {event_label} · {event_date}")
    with pytest.raises(ValidationError):
        build("{monitor_name} {summary}")
    with pytest.raises(ValidationError):
        build("{monitor_name}\nsecond line")
    with pytest.raises(ValidationError):
        build("{monitor_name")
    with pytest.raises(ValidationError):
        build("   ")


def test_template_specs_require_a_name_and_a_valid_config():
    config = EmailTemplateConfig.model_validate({"subject": "{monitor_name}"})
    spec = EmailTemplateSpec(name="  Price mail  ", config=config)
    assert spec.name == "Price mail"
    assert spec.description == ""
    with pytest.raises(ValidationError):
        EmailTemplateSpec(name="   ", config=config)
    with pytest.raises(ValidationError):
        EmailTemplateSpec(name="Price mail", config={"subject": "{nope}"})
    with pytest.raises(ValidationError):
        EmailTemplateSpec(name="Price mail", config=config, enabled=True)
    patch = EmailTemplatePatch(description="Only this")
    assert patch.name is None and patch.config is None
    with pytest.raises(ValidationError):
        EmailTemplatePatch(name="  ")


def test_rename_rejects_a_blank_name():
    assert MonitorRename(name="  Price watch  ").name == "Price watch"
    with pytest.raises(ValidationError):
        MonitorRename(name="   ")
    with pytest.raises(ValidationError):
        MonitorRename(name="x" * 201)
