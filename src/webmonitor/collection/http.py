"""HTML collection through the mandatory ACL egress proxy."""
import asyncio
from time import monotonic

from webmonitor.collection.extraction import extract_fields
from webmonitor.collection.fetch import content_type_base, decode_text, fetch_bounded
from webmonitor.collection.types import (
    MAX_HTML_BYTES,
    CollectionResult,
    analyze_html,
    collection_coverage,
)
from webmonitor.collection.validation import validate_collection
from webmonitor.errors import DomainError
from webmonitor.schemas.monitors import MonitorSpec


async def collect_http(url: str, spec: MonitorSpec | None = None) -> CollectionResult:
    started = monotonic()
    try:
        async with asyncio.timeout(30):
            fetched = await fetch_bounded(url, accept='text/html,application/xhtml+xml',
                                         max_bytes=MAX_HTML_BYTES)
            if fetched.status >= 400:
                raise DomainError('target_http_error', 503 if fetched.status >= 500 else 422,
                                  details={'status_code': fetched.status})
            if fetched.status != 200:
                raise DomainError('target_http_error', 422,
                                  details={'status_code': fetched.status})
            if content_type_base(fetched.headers) not in {'text/html', 'application/xhtml+xml'}:
                raise DomainError('unsupported_content_type', 422)
            html = decode_text(fetched.body, fetched.headers)
            analysis, warnings = analyze_html(html)
            analysis['collection_mode'] = 'http'
            coverage = collection_coverage(spec, warnings, html=html)
            result = CollectionResult(fetched.final_url, html, None, {}, coverage,
                                      int((monotonic() - started) * 1000), warnings, analysis,
                                      body_kind='html')
            if spec:
                result.fields = extract_fields(html, spec, final_url=fetched.final_url)
                validate_collection(spec, result.fields, coverage=coverage)
            return result
    except TimeoutError:
        raise DomainError('collection_timeout', 503) from None
