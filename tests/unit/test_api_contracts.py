"""Request contracts reject ambiguous input before any service call."""
from uuid import uuid4

import pytest
from pydantic import ValidationError

from webmonitor.schemas.api import ApproveRequest, GroupPatch, GroupSpec, PostMessageRequest


def test_message_requires_content_and_a_client_id():
    with pytest.raises(ValidationError):
        PostMessageRequest(content="", client_message_id="abc")
    with pytest.raises(ValidationError):
        PostMessageRequest(content="hello")
    with pytest.raises(ValidationError):
        PostMessageRequest(content="hello", client_message_id="x" * 65)
    assert PostMessageRequest(content="hello", client_message_id="abc").content == "hello"


def test_approval_requires_the_preview_the_user_confirmed():
    assert ApproveRequest(draft_id=uuid4(), revision=3, preview_hash="a" * 64).revision == 3
    with pytest.raises(ValidationError):
        ApproveRequest(draft_id=uuid4(), revision=0, preview_hash="a" * 64)
    with pytest.raises(ValidationError):
        ApproveRequest(draft_id=uuid4(), revision=1)
    with pytest.raises(ValidationError):
        ApproveRequest(draft_id=uuid4(), revision=1, preview_hash="not-a-preview-hash")
    with pytest.raises(ValidationError):
        ApproveRequest(draft_id=uuid4(), revision=1, preview_hash="a" * 64, preview_id=str(uuid4()))


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
