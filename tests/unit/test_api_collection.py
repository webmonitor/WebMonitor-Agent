"""JSON API collection: ordered steps, assertions, pagination and failures."""
import json
from uuid import uuid4

import httpx
import pytest

from webmonitor.collection.api import collect_api
from webmonitor.errors import DomainError
from webmonitor.schemas.monitors import DraftSpec


def json_response(payload, status=200, content_type='application/json'):
    body = json.dumps(payload).encode()
    return httpx.Response(status, headers={'content-type': content_type},
                          stream=httpx.ByteStream(body))


def raw_response(body, status=200, content_type='application/json', headers=None):
    merged = {'content-type': content_type}
    merged.update(headers or {})
    return httpx.Response(status, headers=merged, stream=httpx.ByteStream(body))


def list_field(path='data.list'):
    return {'name': 'items', 'type': 'list', 'semantic': 'Rows', 'path': path,
            'item_fields': [{'name': 'id', 'type': 'text', 'semantic': 'ID', 'path': 'id'}]}


def step(url, step_id='list', method='GET', **request):
    return {'id': step_id, 'request': {'method': method, 'url': url, **request}}


def spec(*, steps, fields=None, assertions=None, pagination=None, coverage='full'):
    return DraftSpec.model_validate({
        'name': 'API monitor', 'url': 'https://page.example.com/list',
        'collection_mode': 'http',
        'source': {'kind': 'json', 'steps': steps,
                   'assertions': assertions or [], 'pagination': pagination},
        'fields': fields or [list_field()],
        'business_key': {'field': 'items', 'item_fields': ['id']},
        'change_rules': {'mode': 'any', 'rules': [{'type': 'list_added', 'field': 'items'}]},
        'schedule': {'interval_seconds': 3600, 'timezone': 'UTC'},
        'notification_group_ids': [str(uuid4())],
        'coverage': {'scope': coverage, 'description': 'Rows'},
    })


def page_body(page, per_page=2, total=8):
    first = (page - 1) * per_page + 1
    return {'code': 200, 'data': {'total': total,
                                  'list': [{'id': str(first + offset)}
                                           for offset in range(per_page)]}}


def paged(page_count, per_page=2, total=8):
    """Serve unique rows for `page_count` pages, then one empty page."""
    def handler(request):
        query = dict(httpx.QueryParams(request.url.query.decode()))
        page = int(query.get('page', 1))
        if page > page_count:
            return json_response({'code': 200, 'data': {'total': total, 'list': []}})
        return json_response(page_body(page, per_page, total))
    return handler


@pytest.mark.asyncio
async def test_steps_bind_earlier_responses_into_later_urls():
    calls = []

    def handler(request):
        calls.append(str(request.url))
        if request.url.path == '/contest/info':
            return json_response({'code': 200, 'data': {'contest_id': '60 370/1'}})
        return json_response({'code': 200, 'data': {'list': [{'id': '9'}]}})

    monitor = spec(
        steps=[step('https://api.example.com/contest/info', 'info'),
               step('https://api.example.com/contest/{{steps.info.data.contest_id}}')],
        assertions=[{'type': 'json_equals', 'path': 'code', 'equals': 200}])
    result = await collect_api(monitor.url, monitor, transport=httpx.MockTransport(handler))
    assert calls[1] == 'https://api.example.com/contest/60%20370%2F1'
    assert result.fields == {'items': [{'id': '9'}]}
    assert result.body_kind == 'json'
    source = result.analysis['source']
    assert source['pages'] == 1
    assert [item['id'] for item in source['steps']] == ['info', 'list']
    assert source['steps'][0]['status'] == 200
    assert source['assertions'] == [{'type': 'json_equals', 'path': 'code', 'passed': True}]
    assert result.coverage == {'scope': 'full', 'description': 'Rows'}
    assert json.loads(result.body)['code'] == 200


@pytest.mark.asyncio
async def test_assertions_reject_business_errors_and_missing_paths():
    mismatch = spec(steps=[step('https://api.example.com/items')],
                    assertions=[{'type': 'json_equals', 'path': 'code', 'equals': 0}])
    with pytest.raises(DomainError) as failure:
        await collect_api(mismatch.url, mismatch, transport=httpx.MockTransport(
            lambda request: json_response({'code': 500, 'data': {'list': [{'id': '1'}]}})))
    assert failure.value.code == 'api_assertion_failed'
    assert failure.value.details == {'path': 'code', 'expected': 0, 'actual': '500'}
    missing = spec(steps=[step('https://api.example.com/items')],
                   assertions=[{'type': 'json_present', 'path': 'data.token'}])
    with pytest.raises(DomainError) as absent:
        await collect_api(missing.url, missing, transport=httpx.MockTransport(
            lambda request: json_response({'code': 200, 'data': {'list': [{'id': '1'}]}})))
    assert absent.value.details == {'path': 'data.token', 'reason': 'missing'}
    graphql = spec(steps=[step('https://api.example.com/graphql', method='POST',
                               body={'query': '{ items { id } }'})])
    with pytest.raises(DomainError) as errors:
        await collect_api(graphql.url, graphql, transport=httpx.MockTransport(
            lambda request: json_response({'errors': [{'message': 'bad'}],
                                           'data': {'list': [{'id': '1'}]}})))
    assert errors.value.details == {'reason': 'graphql_errors'}


@pytest.mark.asyncio
async def test_page_pagination_collects_until_the_api_reports_empty():
    urls = []

    def handler(request):
        urls.append(str(request.url))
        return paged(page_count=4)(request)

    monitor = spec(steps=[step('https://api.example.com/items')],
                   pagination={'kind': 'page', 'page_param': 'page', 'size_param': 'size',
                               'size': 2, 'stop': 'empty', 'max_pages': 5, 'max_items': 100})
    result = await collect_api(monitor.url, monitor,
                               transport=httpx.MockTransport(handler))
    # The first request is the step itself (used for assertions); every stored
    # page is then requested with the pagination parameters.
    assert urls[0] == 'https://api.example.com/items'
    assert urls[1] == 'https://api.example.com/items?page=1&size=2'
    assert urls[2] == 'https://api.example.com/items?page=2&size=2'
    assert urls[5].endswith('page=5&size=2')
    assert len(urls) == 6
    assert [row['id'] for row in result.fields['items']] == [str(n) for n in range(1, 9)]
    assert result.analysis['source']['pages'] == 5
    assert result.analysis['source']['steps'][-1]['pages'] == 5
    assert result.warnings == []
    # Only the first page is stored as evidence.
    assert json.loads(result.body)['data']['list'][0]['id'] == '1'


@pytest.mark.asyncio
async def test_total_reached_stops_without_requesting_another_page():
    calls = []

    def handler(request):
        calls.append(str(request.url))
        return paged(page_count=4)(request)

    monitor = spec(steps=[step('https://api.example.com/items')],
                   pagination={'kind': 'page', 'size_param': 'size', 'size': 2,
                               'total_path': 'data.total', 'stop': 'total_reached',
                               'max_pages': 5, 'max_items': 100})
    result = await collect_api(monitor.url, monitor, transport=httpx.MockTransport(handler))
    assert len(calls) == 5
    assert len(result.fields['items']) == 8
    assert result.analysis['source']['pages'] == 4


@pytest.mark.asyncio
async def test_total_reached_requires_an_integer_total():
    monitor = spec(steps=[step('https://api.example.com/items')],
                   pagination={'kind': 'page', 'total_path': 'data.missing',
                               'stop': 'total_reached', 'max_pages': 3})
    with pytest.raises(DomainError) as error:
        await collect_api(monitor.url, monitor, transport=httpx.MockTransport(
            lambda request: json_response(page_body(1))))
    assert error.value.code == 'api_schema_invalid'
    assert error.value.details == {'reason': 'total_missing'}


@pytest.mark.asyncio
async def test_full_coverage_rejects_truncated_pagination():
    monitor = spec(steps=[step('https://api.example.com/items')], coverage='full',
                   pagination={'kind': 'page', 'size_param': 'size', 'size': 2,
                               'stop': 'empty', 'max_pages': 2, 'max_items': 100})
    with pytest.raises(DomainError) as error:
        await collect_api(monitor.url, monitor, transport=httpx.MockTransport(paged(4)))
    assert error.value.code == 'api_pagination_limit'
    assert error.value.details == {'pages': 2, 'items': 4}


@pytest.mark.asyncio
async def test_bounded_coverage_reports_the_truncation():
    monitor = spec(steps=[step('https://api.example.com/items')], coverage='bounded',
                   pagination={'kind': 'page', 'size_param': 'size', 'size': 2,
                               'stop': 'empty', 'max_pages': 2, 'max_items': 100})
    result = await collect_api(monitor.url, monitor,
                               transport=httpx.MockTransport(paged(4)))
    assert result.warnings == ['pagination_truncated']
    assert len(result.fields['items']) == 4
    assert result.coverage == {'scope': 'bounded', 'description': 'Rows'}


@pytest.mark.asyncio
async def test_max_items_truncates_the_merged_list():
    monitor = spec(steps=[step('https://api.example.com/items')], coverage='bounded',
                   pagination={'kind': 'page', 'size_param': 'size', 'size': 2,
                               'stop': 'empty', 'max_pages': 3, 'max_items': 3})
    result = await collect_api(monitor.url, monitor,
                               transport=httpx.MockTransport(paged(4)))
    assert [row['id'] for row in result.fields['items']] == ['1', '2', '3']
    assert result.warnings == ['pagination_truncated']


@pytest.mark.asyncio
async def test_empty_first_page_fails():
    monitor = spec(steps=[step('https://api.example.com/items')])
    with pytest.raises(DomainError) as error:
        await collect_api(monitor.url, monitor, transport=httpx.MockTransport(
            lambda request: json_response({'code': 200, 'data': {'list': []}})))
    assert error.value.code == 'api_empty_result'
    assert error.value.details == {'field': 'items'}


@pytest.mark.asyncio
async def test_response_failures_map_to_domain_errors():
    monitor = spec(steps=[step('https://api.example.com/items')])

    def html(request):
        return raw_response(b'<html></html>', content_type='text/html')

    def broken(request):
        return raw_response(b'{not json', status=200)

    def server(request):
        return raw_response(b'{}', status=500)

    cases = ((html, 'unsupported_content_type', {'content_type': 'text/html'}),
             (broken, 'api_schema_invalid', {'reason': 'invalid_json'}),
             (server, 'target_http_error', {'status_code': 500}))
    for handler, code, details in cases:
        with pytest.raises(DomainError) as error:
            await collect_api(monitor.url, monitor,
                              transport=httpx.MockTransport(handler))
        assert error.value.code == code
        for key, value in details.items():
            assert error.value.details[key] == value


@pytest.mark.asyncio
async def test_post_body_and_headers_travel_and_303_switches_to_get():
    seen = []

    def handler(request):
        seen.append((request.method, str(request.url), request.headers.get('content-type'),
                     request.content))
        if request.url.path == '/search':
            return raw_response(b'', status=303, headers={'location': '/results'})
        return json_response({'code': 200, 'data': {'list': [{'id': '1'}]}})

    monitor = spec(steps=[step('https://api.example.com/search', method='POST',
                               headers={'Accept-Language': 'zh-CN'},
                               body={'query': 'notice'})])
    result = await collect_api(monitor.url, monitor,
                               transport=httpx.MockTransport(handler))
    assert seen[0][0] == 'POST'
    assert json.loads(seen[0][3]) == {'query': 'notice'}
    assert seen[0][2] == 'application/json'
    assert seen[1][0] == 'GET' and seen[1][3] == b''
    assert seen[1][1] == 'https://api.example.com/results'
    assert result.analysis['source']['steps'][0]['url'] == 'https://api.example.com/search'


@pytest.mark.asyncio
async def test_unresolved_template_reports_the_step_and_token():
    monitor = spec(steps=[step('https://api.example.com/info', 'info'),
                          step('https://api.example.com/items/{{steps.info.data.id}}')])
    with pytest.raises(DomainError) as error:
        await collect_api(monitor.url, monitor, transport=httpx.MockTransport(
            lambda request: json_response({'code': 200, 'data': {}})))
    assert error.value.code == 'api_template_unresolved'
    assert error.value.details == {'step': 'info', 'token': '{{steps.info.data.id}}'}
