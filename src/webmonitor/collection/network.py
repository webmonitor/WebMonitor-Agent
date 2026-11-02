"""Shape a captured xhr/fetch response into one bounded, model-readable candidate."""
import json
from typing import Any

from webmonitor.collection.json_extract import json_summary
from webmonitor.schemas.monitors import REQUEST_HEADER_ALLOWLIST

MAX_REQUEST_BODY = 8192
MAX_SAMPLE = 8192


def network_candidate(*, method: str, url: str, status: int, content_type: str,
                      headers: dict[str, str], request_body: str | None,
                      body: bytes) -> dict[str, Any]:
    parsed = json.loads(body)
    return {
        'method': method,
        'url': url,
        'status': status,
        'content_type': content_type,
        # Request headers are reported so the agent can replay the honest minimum.
        'headers': {name: value for name, value in headers.items()
                    if name.casefold() in REQUEST_HEADER_ALLOWLIST},
        'request_body': None if request_body is None else request_body[:MAX_REQUEST_BODY],
        'sample': json.dumps(parsed, ensure_ascii=False)[:MAX_SAMPLE],
        'summary': json_summary(parsed),
        'size': len(body),
    }
