"""Each preview hash covers exactly the frozen facts its confirmation relies on."""
from webmonitor.models import utc_now
from webmonitor.schemas.monitors import content_hash
from webmonitor.services.drafts import DELIVERY_KEYS, EXTRACTION_KEYS


def extraction_payload(**overrides):
    base = {
        "preview_id": "preview-1",
        "spec_revision": 2,
        "spec_hash": "a" * 64,
        "extracted_data": {"title": "A"},
        "coverage": {"scope": "full", "description": "All rows"},
        "final_url": "https://example.com/",
        "evidence_refs": [{"kind": "html", "bucket": "b", "object_key": "k",
                           "content_type": "text/plain", "size_bytes": 3, "sha256": "c" * 64}],
        "rule_simulation": {"triggered": False},
        "source": None,
        "warnings": [],
        "created_at": utc_now().isoformat(),
        "expires_at": utc_now().isoformat(),
    }
    base.update(overrides)
    return base


def delivery_payload(**overrides):
    base = {
        "preview_id": "preview-2",
        "settings_revision": 1,
        "settings_hash": "d" * 64,
        "channel": "email",
        "webhook_url": None,
        "webhook_body": None,
        "template_id": None,
        "template_name": None,
        "template_hash": "e" * 64,
        "rendered_emails": [{"event_type": "content_changed", "subject": "s",
                             "html": "<p>x</p>", "text": "x", "preview_html": "<p>x</p>"}],
        "recipients": ["ops@example.com"],
        "recipient_sources": [{"email": "ops@example.com", "group_ids": ["g-1"]}],
        "warnings": [],
        "created_at": utc_now().isoformat(),
        "expires_at": utc_now().isoformat(),
    }
    base.update(overrides)
    return base


def digest(payload: dict, keys: tuple[str, ...]) -> str:
    return content_hash({key: payload.get(key) for key in keys})


def test_extraction_hash_changes_when_any_collected_fact_changes():
    reference = digest(extraction_payload(), EXTRACTION_KEYS)
    changed = [
        extraction_payload(preview_id="replacement-preview"),
        extraction_payload(final_url="https://example.com/other"),
        extraction_payload(spec_hash="b" * 64),
        extraction_payload(spec_revision=3),
        extraction_payload(extracted_data={"title": "B"}),
        extraction_payload(coverage={"scope": "bounded", "description": "Some rows"}),
        extraction_payload(evidence_refs=[]),
        extraction_payload(rule_simulation={"triggered": True}),
        extraction_payload(warnings=["pagination_coverage_unproven"]),
    ]
    assert all(digest(item, EXTRACTION_KEYS) != reference for item in changed)
    assert digest(extraction_payload(), EXTRACTION_KEYS) == reference


def test_extraction_hash_ignores_timestamps_and_delivery_fields():
    reference = digest(extraction_payload(), EXTRACTION_KEYS)
    assert digest(extraction_payload(created_at="2020-01-01T00:00:00+00:00"),
                  EXTRACTION_KEYS) == reference
    assert digest(extraction_payload(recipients=["someone@example.com"]),
                  EXTRACTION_KEYS) == reference


def test_delivery_hash_changes_when_any_delivery_fact_changes():
    reference = digest(delivery_payload(), DELIVERY_KEYS)
    changed = [
        delivery_payload(preview_id="replacement-preview"),
        delivery_payload(settings_revision=2),
        delivery_payload(settings_hash="f" * 64),
        delivery_payload(channel="webhook"),
        delivery_payload(webhook_url="https://hooks.example.com/ops"),
        delivery_payload(webhook_body={"event": {"type": "content_changed"}}),
        delivery_payload(template_id="00000000-0000-4000-8000-000000000001"),
        delivery_payload(template_name="Design"),
        delivery_payload(template_hash="0" * 64),
        delivery_payload(rendered_emails=[]),
        delivery_payload(recipients=["other@example.com"]),
        delivery_payload(recipient_sources=[{"email": "ops@example.com",
                                            "group_ids": ["different-group"]}]),
        delivery_payload(warnings=["delivery_preview_failed:template_unavailable"]),
    ]
    assert all(digest(item, DELIVERY_KEYS) != reference for item in changed)
    assert digest(delivery_payload(), DELIVERY_KEYS) == reference


def test_delivery_hash_ignores_the_collected_page():
    reference = digest(delivery_payload(), DELIVERY_KEYS)
    assert digest(delivery_payload(extracted_data={"title": "B"}), DELIVERY_KEYS) == reference
