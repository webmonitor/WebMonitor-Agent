"""Evidence downloads keep the file type their body actually has."""
from webmonitor.api.routes.evidence import evidence_disposition, evidence_media_type


def reference(kind: str, content_type: str, sha: str = "a" * 64) -> dict:
    return {"kind": kind, "content_type": content_type, "sha256": sha}


def test_html_archive_downloads_with_an_html_extension():
    item = reference("html", "text/html; charset=utf-8")
    assert evidence_disposition(item) == 'attachment; filename="aaaaaaaaaaaaaaaa.html"'
    assert evidence_media_type(item) == "text/html; charset=utf-8"


def test_existing_html_references_keep_their_extension():
    # A stored content type outside the known set is served as an opaque download.
    item = reference("html", "text/plain; charset=utf-8", sha="b" * 64)
    assert evidence_disposition(item).endswith('.html"')
    assert evidence_media_type(item) == "application/octet-stream"


def test_json_archive_keeps_a_json_extension():
    item = reference("json", "application/json")
    assert evidence_disposition(item) == 'attachment; filename="aaaaaaaaaaaaaaaa.json"'


def test_screenshot_opens_inline_as_png():
    item = reference("screenshot", "image/png")
    disposition = evidence_disposition(item)
    assert disposition.startswith("inline;")
    assert disposition.endswith('.png"')
