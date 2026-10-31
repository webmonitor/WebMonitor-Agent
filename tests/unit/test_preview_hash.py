"""A preview hash covers exactly the frozen facts a confirmation relies on."""
from webmonitor.models import utc_now
from webmonitor.services.drafts import preview_hash


def payload(**overrides):
    base = {
        "revision": 2,
        "spec_hash": "a" * 64,
        "extracted_data": {"title": "A"},
        "coverage": {"scope": "full", "description": "All rows"},
        "final_url": "https://example.com/",
        "evidence_refs": [{"kind": "html", "bucket": "b", "object_key": "k",
                           "content_type": "text/plain", "size_bytes": 3, "sha256": "c" * 64}],
        "rule_simulation": {"triggered": False},
        "rendered_emails": [{"event_type": "content_changed", "subject": "s",
                             "html": "<p>x</p>", "text": "x"}],
        "recipients": ["ops@example.com"],
        "warnings": [],
        "created_at": utc_now().isoformat(),
        "expires_at": utc_now().isoformat(),
    }
    base.update(overrides)
    return base


def test_hash_changes_when_any_frozen_fact_changes():
    reference = preview_hash(payload())
    changed = [
        payload(preview_id="replacement-preview"),
        payload(final_url="https://example.com/other"),
        payload(recipient_sources=[{"email": "ops@example.com", "group_ids": ["different-group"]}]),
        payload(spec_hash="b" * 64),
        payload(extracted_data={"title": "B"}),
        payload(coverage={"scope": "bounded", "description": "Some rows"}),
        payload(evidence_refs=[]),
        payload(rule_simulation={"triggered": True}),
        payload(rendered_emails=[]),
        payload(recipients=["other@example.com"]),
        payload(warnings=["pagination_coverage_unproven"]),
        payload(revision=3),
    ]
    assert all(preview_hash(item) != reference for item in changed)
    assert preview_hash(payload()) == reference

