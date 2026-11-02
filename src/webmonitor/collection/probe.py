"""Read-only page and request probes for the agent's discovery phase.

`probe` fetches a page once and reports what kind of payload it serves; `replay`
sends one concrete request and summarizes the JSON it returns. Neither writes
database rows or evidence.
"""
import json
from typing import Any

import httpx
from bs4 import BeautifulSoup, Comment

from webmonitor.collection.fetch import content_type_base, decode_text, fetch_bounded
from webmonitor.collection.json_extract import json_summary
from webmonitor.collection.types import MAX_HTML_BYTES
from webmonitor.errors import DomainError
from webmonitor.schemas.monitors import ApiRequest, canonical_json

MAX_JSON_BYTES = 5 * 1024 * 1024
PROBE_ACCEPT = 'text/html,application/xhtml+xml,application/json;q=0.9,*/*;q=0.5'
REPLAY_ACCEPT = 'application/json,text/html;q=0.8'
TEXT_SAMPLE = 2000
JSON_SAMPLE = 8192


def _json_media(media_type: str) -> bool:
    return media_type == 'application/json' or media_type.endswith('+json')


def _markers(body: bytes) -> dict:
    return {
        'next_data': b'id="__NEXT_DATA__"' in body,
        'next_f': b'self.__next_f.push' in body,
        'root': b'id="root"' in body,
        'app': b'id="app"' in body,
        'ld_json': b'type="application/ld+json"' in body,
    }


def _json_payload(body: bytes) -> tuple[dict | None, str | None]:
    try:
        parsed: Any = json.loads(body)
    except ValueError:
        return None, None
    return json_summary(parsed), json.dumps(parsed, ensure_ascii=False)[:JSON_SAMPLE]


async def probe(url: str, *, transport: httpx.AsyncBaseTransport | None = None) -> dict:
    """One bounded fetch; the result is already bounded and safe to hand to a model."""
    fetched = await fetch_bounded(url, accept=PROBE_ACCEPT, max_bytes=MAX_HTML_BYTES,
                                  transport=transport)
    media_type = content_type_base(fetched.headers)
    text = decode_text(fetched.body, fetched.headers)
    report = {
        'url': url,
        'final_url': fetched.final_url,
        'status': fetched.status,
        'content_type': media_type,
        'bytes': len(fetched.body),
        'title': None,
        'text_sample': '',
        'markers': _markers(fetched.body),
        'comments': [],
        'scripts': [],
        'json_summary': None,
        'json_sample': None,
    }
    if _json_media(media_type):
        report['json_summary'], report['json_sample'] = _json_payload(fetched.body)
        return report
    soup = BeautifulSoup(text, 'lxml')
    report['title'] = soup.title.get_text(strip=True) if soup.title else None
    report['text_sample'] = soup.get_text(' ', strip=True)[:TEXT_SAMPLE]
    report['comments'] = [str(node).strip()[:500] for node in soup.find_all(
        string=lambda value: isinstance(value, Comment))[:5]]
    report['scripts'] = [str(node.get('src', 'inline'))[:1000]
                         for node in soup.find_all('script', limit=20)]
    return report


async def replay(request: ApiRequest, *,
                 transport: httpx.AsyncBaseTransport | None = None) -> dict:
    """Send one request; a non-200 status is returned so the agent can assert on it."""
    if '{{' in request.url:
        raise DomainError('validation_failed', 422, details={'field': 'url'})
    headers = dict(request.headers)
    payload = None
    if request.method == 'POST' and request.body is not None:
        payload = canonical_json(request.body).encode('utf-8')
        headers.setdefault('content-type', 'application/json')
    fetched = await fetch_bounded(request.url, method=request.method, headers=headers,
                                  body=payload, accept=REPLAY_ACCEPT,
                                  max_bytes=MAX_JSON_BYTES, transport=transport)
    media_type = content_type_base(fetched.headers)
    report = {
        'status': fetched.status,
        'final_url': fetched.final_url,
        'content_type': media_type,
        'bytes': len(fetched.body),
        'json_summary': None,
        'json_sample': None,
        'text_sample': None,
    }
    if _json_media(media_type):
        report['json_summary'], report['json_sample'] = _json_payload(fetched.body)
    else:
        report['text_sample'] = decode_text(fetched.body, fetched.headers)[:TEXT_SAMPLE]
    return report
