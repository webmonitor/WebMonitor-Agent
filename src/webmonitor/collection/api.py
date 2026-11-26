"""JSON API collection: ordered requests, assertions and page/cursor/offset pagination.

Every step runs through the same bounded egress transport as HTML collection.
Only the last step is asserted on and paginated; earlier steps exist to bind
values for later URLs. Every actual page is asserted before extraction.
"""
import asyncio
import json
from time import monotonic
from typing import Any
from urllib.parse import parse_qsl, quote, urlencode, urlsplit, urlunsplit

import httpx

from webmonitor.collection.extraction import (
    MISSING,
    NormalizedResultBudget,
    check_normalized_field,
)
from webmonitor.collection.fetch import (
    FetchResult,
    conditional_headers,
    content_type_base,
    decode_text,
    fetch_bounded,
    validator_from_headers,
)
from webmonitor.collection.json_extract import extract_json_field, extract_json_fields, resolve_path
from webmonitor.collection.types import CollectionResult, deletion_scope
from webmonitor.collection.validation import validate_collection
from webmonitor.errors import DomainError
from webmonitor.schemas.monitors import (
    REQUEST_TEMPLATE,
    ApiRequest,
    ApiSource,
    MonitorSpec,
    CursorPagination,
    Pagination,
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
                transport: httpx.AsyncBaseTransport | None,
                validator: dict | None = None) -> tuple[FetchResult, Any]:
    headers = dict(request.headers)
    headers.update(conditional_headers(validator))
    payload = None
    if request.body is not None:
        payload = canonical_json(request.body).encode('utf-8')
        headers.setdefault('content-type', 'application/json')
    fetched = await fetch_bounded(url, method=request.method, headers=headers, body=payload,
                                  accept='application/json', max_bytes=MAX_JSON_BYTES,
                                  transport=transport)
    if fetched.status == 304 and validator:
        return fetched, None
    if fetched.status != 200:
        raise DomainError('target_http_error', 503 if fetched.status >= 500 else 422,
                          details={'status_code': fetched.status})
    media_type = content_type_base(fetched.headers)
    if media_type != 'application/json' and not media_type.endswith('+json'):
        raise DomainError('unsupported_content_type', 422,
                          details={'content_type': media_type})
    try:
        # Parsing a bounded response can still monopolize the event loop.
        return fetched, await asyncio.to_thread(json.loads, fetched.body)
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


def _page_request(request: ApiRequest, url: str, pagination: Pagination,
                  token: str | int | None) -> tuple[str, ApiRequest]:
    if pagination.kind == 'page':
        parameter = pagination.page_param
    elif pagination.kind == 'cursor':
        parameter = pagination.cursor_param
    else:
        parameter = pagination.offset_param
    replaced = {parameter}
    if pagination.size_param is not None:
        replaced.add(pagination.size_param)
    if pagination.location == 'body':
        body = dict(request.body or {})
        body.pop(parameter, None)
        if token is not None:
            body[parameter] = token
        if pagination.size_param is not None and pagination.size is not None:
            body[pagination.size_param] = pagination.size
        return url, request.model_copy(update={'body': body})
    parts = urlsplit(url)
    query = [(key, value) for key, value in parse_qsl(parts.query, keep_blank_values=True)
             if key not in replaced]
    if token is not None:
        query.append((parameter, str(token)))
    if pagination.size_param is not None and pagination.size is not None:
        query.append((pagination.size_param, str(pagination.size)))
    return urlunsplit(parts._replace(query=urlencode(query))), request


def _next_cursor(body: Any, pagination: CursorPagination) -> str | int | float | None:
    try:
        value = resolve_path(body, pagination.next_cursor_path)
    except (KeyError, IndexError, TypeError):
        return None
    if value is None or value == '':
        return None
    if isinstance(value, bool) or not isinstance(value, (str, int, float)):
        raise DomainError('api_schema_invalid', 422, details={'reason': 'cursor_invalid'})
    return value


def _total(body: Any, pagination: Pagination) -> int:
    try:
        candidate = resolve_path(body, pagination.total_path)
    except (KeyError, IndexError, TypeError):
        raise DomainError('api_schema_invalid', 422,
                          details={'reason': 'total_missing'}) from None
    if isinstance(candidate, bool) or not isinstance(candidate, int):
        raise DomainError('api_schema_invalid', 422, details={'reason': 'total_missing'})
    if candidate < 0:
        raise DomainError('api_schema_invalid', 422, details={'reason': 'total_invalid'})
    return candidate


async def _paginate(request: ApiRequest, step: dict, pagination: Pagination,
                    spec: MonitorSpec, *, transport: httpx.AsyncBaseTransport | None
                    ) -> tuple[dict, int, bool, bool, FetchResult, FetchResult, list[dict]]:
    if spec.source is None:
        raise DomainError('validation_failed', 422, details={'field': 'source'})
    list_field = next(field for field in spec.fields if field.type == 'list')
    assertions: list[dict] = []
    fields = {}
    budget = NormalizedResultBudget()
    items: list = []
    total = None
    if pagination.kind == 'page':
        token = pagination.start_page
    elif pagination.kind == 'cursor':
        token = pagination.start_cursor
    else:
        token = pagination.start_offset
    pages = 0
    truncated = False
    converged = False
    first: FetchResult | None = None
    last: FetchResult | None = None
    while True:
        pages += 1
        request_url, page_request = _page_request(request, step['url'], pagination, token)
        fetched, body = await _send(page_request, request_url, transport=transport)
        current_assertions = await asyncio.to_thread(_assertions, spec.source, body)
        if first is None:
            assertions = current_assertions
            first = fetched
            for field in spec.fields:
                if field.type == 'list':
                    continue
                value = await asyncio.to_thread(
                    extract_json_field, body, field, fetched.final_url, field.name)
                if value is not MISSING:
                    budget.add(field.name, value)
                    fields[field.name] = value
            if pagination.stop == 'total_reached':
                total = _total(body, pagination)
        last = fetched
        # One extra row proves truncation without normalizing the rest of a page.
        remaining = pagination.max_items - len(items)
        rows = await asyncio.to_thread(
            extract_json_field, body, list_field, fetched.final_url, list_field.name,
            row_limit=remaining + 1, prior_rows=len(items))
        rows = [] if rows is MISSING else rows
        items.extend(rows)
        check_normalized_field(list_field.name, items)
        if pages == 1 and not items and not list_field.allow_empty:
            raise DomainError('api_empty_result', 422, details={'field': list_field.name})
        if total is not None:
            if len(items) > total:
                raise DomainError('api_schema_invalid', 422,
                                  details={'reason': 'total_exceeded'})
            if len(items) == total:
                converged = True
                break
        if len(items) > pagination.max_items:
            del items[pagination.max_items:]
            truncated = True
            break
        next_cursor = _next_cursor(body, pagination) if pagination.kind == 'cursor' else None
        if pagination.kind == 'cursor' and next_cursor is None:
            if pagination.stop == 'total_reached':
                truncated = True
            else:
                converged = True
            break
        if pagination.stop == 'empty' and not rows:
            converged = True
            break
        if (pagination.stop == 'empty' and pagination.size is not None
                and len(rows) < pagination.size):
            converged = True
            break
        if len(items) == pagination.max_items or pages >= pagination.max_pages:
            truncated = True
            break
        if pagination.kind == 'page':
            token += 1
        elif pagination.kind == 'offset':
            token += len(rows)
        else:
            if next_cursor == token:
                raise DomainError('api_schema_invalid', 422,
                                  details={'reason': 'cursor_not_progressing'})
            token = next_cursor
    budget.add(list_field.name, items)
    fields[list_field.name] = items
    return fields, pages, truncated, converged, first, last, assertions


async def collect_api(url: str, spec: MonitorSpec, *,
                      transport: httpx.AsyncBaseTransport | None = None,
                      validator: dict | None = None) -> CollectionResult:
    source = spec.source
    if source is None:
        raise DomainError('validation_failed', 422, details={'field': 'source'})
    started = monotonic()
    try:
        async with asyncio.timeout(TOTAL_TIMEOUT_SECONDS):
            bodies: dict[str, Any] = {}
            steps: list[dict] = []
            for step in source.steps[:-1]:
                request_url = _resolve(step.request.url, bodies)
                fetched, body = await _send(step.request, request_url, transport=transport)
                bodies[step.id] = body
                steps.append({'id': step.id, 'method': step.request.method,
                              'url': request_url, 'status': fetched.status, 'pages': 1})
            final_step = source.steps[-1]
            request_url = _resolve(final_step.request.url, bodies)
            if source.pagination is None:
                conditional = len(source.steps) == 1
                page_one, last_body = await _send(final_step.request, request_url,
                                                  transport=transport,
                                                  validator=validator if conditional else None)
                if page_one.status == 304:
                    return CollectionResult(page_one.final_url, None, None, {},
                        spec.coverage.model_dump(), int((monotonic() - started) * 1000), [],
                        {'collection_mode': 'json', 'not_modified': True}, body_kind='json',
                        not_modified=True,
                        validator=validator_from_headers(page_one.headers) or validator)
                last = page_one
                steps.append({'id': final_step.id, 'method': final_step.request.method,
                              'url': request_url, 'status': page_one.status, 'pages': 1})
                assertions = await asyncio.to_thread(_assertions, source, last_body)
                fields = await asyncio.to_thread(
                    extract_json_fields, last_body, spec, page_one.final_url)
                for field in spec.fields:
                    if (field.type == 'list' and not fields.get(field.name)
                            and not field.allow_empty):
                        raise DomainError('api_empty_result', 422,
                                          details={'field': field.name})
                pages, truncated = 1, False
            else:
                fields, pages, truncated, converged, page_one, last, assertions = await _paginate(
                    final_step.request, {'url': request_url}, source.pagination, spec,
                    transport=transport)
                steps.append({'id': final_step.id, 'method': final_step.request.method,
                              'url': request_url, 'status': page_one.status, 'pages': pages})
                if not converged and spec.coverage.scope == 'full':
                    list_field = next(field for field in spec.fields if field.type == 'list')
                    raise DomainError('api_pagination_limit', 422,
                                      details={'pages': pages,
                                               'items': len(fields[list_field.name])})
            warnings = ['pagination_truncated'] if truncated else []
            coverage = deletion_scope(
                spec,
                {'scope': spec.coverage.scope, 'description': spec.coverage.description},
                warnings)
            analysis = {
                'collection_mode': 'json',
                'page_url': url,
                'source': {'kind': 'json', 'steps': steps, 'assertions': assertions,
                           'pages': pages},
            }
            evidence = await asyncio.to_thread(decode_text, page_one.body, page_one.headers)
            result = CollectionResult(last.final_url, evidence, None, fields, coverage,
                                      int((monotonic() - started) * 1000), warnings, analysis,
                                      body_kind='json')
            result.validator = validator_from_headers(last.headers) if len(source.steps) == 1 and source.pagination is None else {}
            await asyncio.to_thread(validate_collection, spec, fields, coverage=coverage)
            return result
    except TimeoutError:
        raise DomainError('collection_timeout', 503) from None
