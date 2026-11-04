"""JSON API collection: ordered requests, assertions and page pagination.

Every step runs through the same bounded egress transport as HTML collection.
Only the last response is asserted on and paginated; earlier steps exist to bind
values for later URLs.
"""
import asyncio
import json
from time import monotonic
from typing import Any
from urllib.parse import parse_qsl, quote, urlencode, urlsplit, urlunsplit

import httpx

from webmonitor.collection.extraction import MISSING
from webmonitor.collection.fetch import FetchResult, content_type_base, decode_text, fetch_bounded
from webmonitor.collection.json_extract import extract_json_field, extract_json_fields, resolve_path
from webmonitor.collection.types import CollectionResult
from webmonitor.collection.validation import validate_collection
from webmonitor.errors import DomainError
from webmonitor.schemas.monitors import (
    REQUEST_TEMPLATE,
    ApiRequest,
    ApiSource,
    MonitorSpec,
    PagePagination,
    canonical_json,
)

MAX_JSON_BYTES = 5 * 1024 * 1024
TOTAL_TIMEOUT_SECONDS = 60


def _resolve(url: str, bodies: dict[str, Any]) -> str:
    def substitute(match) -> str:
        step_id, path, token = match.group('step'), match.group('path'), match.group(0)
        detail = {'step': step_id, 'token': token}
        if step_id not in bodies:
            raise DomainError('api_template_unresolved', 422, details=detail)
        try:
            value = resolve_path(bodies[step_id], path)
        except (KeyError, IndexError, TypeError):
            raise DomainError('api_template_unresolved', 422, details=detail) from None
        if value is None or isinstance(value, (dict, list)):
            raise DomainError('api_template_unresolved', 422, details=detail)
        return quote(str(value), safe='')

    return REQUEST_TEMPLATE.sub(substitute, url)


async def _send(request: ApiRequest, url: str, *,
                transport: httpx.AsyncBaseTransport | None) -> tuple[FetchResult, Any]:
    headers = dict(request.headers)
    payload = None
    if request.body is not None:
        payload = canonical_json(request.body).encode('utf-8')
        headers.setdefault('content-type', 'application/json')
    fetched = await fetch_bounded(url, method=request.method, headers=headers, body=payload,
                                  accept='application/json', max_bytes=MAX_JSON_BYTES,
                                  transport=transport)
    if fetched.status != 200:
        raise DomainError('target_http_error', 503 if fetched.status >= 500 else 422,
                          details={'status_code': fetched.status})
    media_type = content_type_base(fetched.headers)
    if media_type != 'application/json' and not media_type.endswith('+json'):
        raise DomainError('unsupported_content_type', 422,
                          details={'content_type': media_type})
    try:
        return fetched, json.loads(fetched.body)
    except ValueError:
        raise DomainError('api_schema_invalid', 422, details={'reason': 'invalid_json'}) from None


def _equal(actual: Any, expected: Any) -> bool:
    # JSON true and 1 are different business values even though Python equates them.
    if isinstance(actual, bool) or isinstance(expected, bool):
        return type(actual) is type(expected) and actual == expected
    return actual == expected


def _assertions(source: ApiSource, body: Any) -> list[dict]:
    passed = []
    for assertion in source.assertions:
        try:
            actual = resolve_path(body, assertion.path)
        except (KeyError, IndexError, TypeError):
            raise DomainError('api_assertion_failed', 422,
                              details={'path': assertion.path, 'reason': 'missing'}) from None
        if assertion.type == 'json_equals' and not _equal(actual, assertion.equals):
            raise DomainError('api_assertion_failed', 422, details={
                'path': assertion.path, 'expected': assertion.equals,
                'actual': json.dumps(actual, ensure_ascii=False)[:200]})
        passed.append({'type': assertion.type, 'path': assertion.path, 'passed': True})
    if isinstance(body, dict):
        errors = body.get('errors')
        if isinstance(errors, list) and errors:
            raise DomainError('api_assertion_failed', 422, details={'reason': 'graphql_errors'})
    return passed


def _page_url(url: str, pagination: PagePagination, page: int) -> str:
    parts = urlsplit(url)
    replaced = {pagination.page_param}
    if pagination.size_param is not None:
        replaced.add(pagination.size_param)
    query = [(key, value) for key, value in parse_qsl(parts.query, keep_blank_values=True)
             if key not in replaced]
    query.append((pagination.page_param, str(page)))
    if pagination.size_param is not None and pagination.size is not None:
        query.append((pagination.size_param, str(pagination.size)))
    return urlunsplit(parts._replace(query=urlencode(query)))


def _total(body: Any, pagination: PagePagination) -> int:
    try:
        candidate = resolve_path(body, pagination.total_path)
    except (KeyError, IndexError, TypeError):
        raise DomainError('api_schema_invalid', 422,
                          details={'reason': 'total_missing'}) from None
    if isinstance(candidate, bool) or not isinstance(candidate, int):
        raise DomainError('api_schema_invalid', 422, details={'reason': 'total_missing'})
    return candidate


async def _paginate(request: ApiRequest, step: dict, pagination: PagePagination,
                    spec: MonitorSpec, *, transport: httpx.AsyncBaseTransport | None
                    ) -> tuple[dict, int, bool, FetchResult, FetchResult]:
    list_field = next(field for field in spec.fields if field.type == 'list')
    fields = {}
    items: list = []
    total = None
    page = pagination.start_page
    pages = 0
    truncated = False
    first: FetchResult | None = None
    last: FetchResult | None = None
    while True:
        pages += 1
        # Every page, including the first, is requested with the pagination
        # parameters so the step URL never decides how many rows arrive.
        fetched, body = await _send(request, _page_url(step['url'], pagination, page),
                                    transport=transport)
        if first is None:
            first = fetched
            for field in spec.fields:
                if field.type == 'list':
                    continue
                value = extract_json_field(body, field, fetched.final_url, field.name)
                if value is not MISSING:
                    fields[field.name] = value
            if pagination.stop == 'total_reached':
                total = _total(body, pagination)
        last = fetched
        rows = extract_json_field(body, list_field, fetched.final_url, list_field.name)
        rows = [] if rows is MISSING else rows
        items.extend(rows)
        if pages == 1 and not items:
            raise DomainError('api_empty_result', 422, details={'field': list_field.name})
        if not rows and pagination.stop == 'empty':
            break
        if total is not None and len(items) >= total:
            break
        if len(items) > pagination.max_items:
            del items[pagination.max_items:]
            truncated = True
        elif len(items) >= pagination.max_items:
            truncated = True
        elif pages >= pagination.max_pages:
            truncated = True
        if truncated:
            break
        page += 1
    fields[list_field.name] = items
    if truncated and spec.coverage.scope == 'full':
        raise DomainError('api_pagination_limit', 422,
                          details={'pages': pages, 'items': len(items)})
    return fields, pages, truncated, first, last


async def collect_api(url: str, spec: MonitorSpec, *,
                      transport: httpx.AsyncBaseTransport | None = None) -> CollectionResult:
    source = spec.source
    if source is None:
        raise DomainError('validation_failed', 422, details={'field': 'source'})
    started = monotonic()
    try:
        async with asyncio.timeout(TOTAL_TIMEOUT_SECONDS):
            bodies: dict[str, Any] = {}
            steps: list[dict] = []
            last: FetchResult | None = None
            last_body: Any = None
            for step in source.steps:
                request_url = _resolve(step.request.url, bodies)
                fetched, body = await _send(step.request, request_url, transport=transport)
                bodies[step.id] = body
                steps.append({'id': step.id, 'method': step.request.method,
                              'url': request_url, 'status': fetched.status, 'pages': 1})
                last, last_body = fetched, body
            # The last step's own response is the first page without pagination.
            page_one = last
            assertions = _assertions(source, last_body)
            if source.pagination is None:
                fields = extract_json_fields(last_body, spec, page_one.final_url)
                for field in spec.fields:
                    if field.type == 'list' and not fields.get(field.name):
                        raise DomainError('api_empty_result', 422,
                                          details={'field': field.name})
                pages, truncated = 1, False
            else:
                fields, pages, truncated, page_one, last = await _paginate(
                    source.steps[-1].request, steps[-1], source.pagination, spec,
                    transport=transport)
                steps[-1]['pages'] = pages
            coverage = {'scope': spec.coverage.scope, 'description': spec.coverage.description}
            warnings = ['pagination_truncated'] if truncated else []
            analysis = {
                'collection_mode': 'json',
                'page_url': url,
                'source': {'kind': 'json', 'steps': steps, 'assertions': assertions,
                           'pages': pages},
            }
            result = CollectionResult(last.final_url,
                                      decode_text(page_one.body, page_one.headers),
                                      None, fields, coverage,
                                      int((monotonic() - started) * 1000), warnings, analysis,
                                      body_kind='json')
            try:
                validate_collection(spec, fields, coverage=coverage)
            except DomainError as exc:
                exc.collection_result = result
                raise
            return result
    except TimeoutError:
        raise DomainError('collection_timeout', 503) from None
