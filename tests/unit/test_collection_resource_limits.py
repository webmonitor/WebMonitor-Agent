"""Resource ceilings apply before and during untrusted response normalization."""
import asyncio
import json
import threading
import time

import httpx
import pytest
from pydantic import ValidationError

import webmonitor.collection.api as api_collection
import webmonitor.collection.diff as rule_diff
import webmonitor.collection.extraction as html_extraction
import webmonitor.collection.http as http_collection
import webmonitor.collection.json_extract as json_extraction
from webmonitor.collection.diff import evaluate_rules
from webmonitor.collection.extraction import NormalizedResultBudget
from webmonitor.collection.fetch import FetchResult
from webmonitor.collection.json_extract import extract_json_field
from webmonitor.errors import DomainError
from webmonitor.schemas.monitors import ChangeRules, FieldSpec, MonitorSpec


def text_field(name='value', *, path=None):
    location = {'path': path or name} if path is not None else {'selector': '.value'}
    return {'name': name, 'type': 'text', 'semantic': name, **location}


def monitor(fields, rules, *, mode='http', browser_steps=None, source=None,
            business_key=None, coverage='bounded'):
    return MonitorSpec.model_validate({
        'name': 'Resource limits', 'url': 'https://example.com/watch',
        'collection_mode': mode, 'fields': fields, 'business_key': business_key,
        'change_rules': {'mode': 'any', 'rules': rules},
        'coverage': {'scope': coverage, 'description': 'Observed values'},
        'browser_steps': browser_steps or [], 'source': source,
    })


def json_list_field(**options):
    return FieldSpec.model_validate({
        'name': 'items', 'type': 'list', 'semantic': 'Items', 'path': 'rows',
        'item_fields': [{'name': 'id', 'type': 'text', 'semantic': 'ID', 'path': 'id'}],
        **options,
    })


def test_monitor_collection_contract_acceptance_boundaries():
    fields = [text_field(f'f{index}') for index in range(64)]
    rules = [{'type': 'text_changed', 'field': 'f0'}]
    assert len(monitor(fields, rules).fields) == 64
    with pytest.raises(ValidationError):
        monitor(fields + [text_field('overflow')], rules)

    assert len(ChangeRules.model_validate({'mode': 'any', 'rules': [
        {'type': 'text_changed', 'field': 'value'} for _ in range(32)]}).rules) == 32
    with pytest.raises(ValidationError):
        ChangeRules.model_validate({'mode': 'any', 'rules': [
            {'type': 'text_changed', 'field': 'value'} for _ in range(33)]})

    steps = [{'type': 'scroll', 'max_steps': 1} for _ in range(20)]
    assert len(monitor([text_field()], [{'type': 'text_changed', 'field': 'value'}],
                       mode='browser', browser_steps=steps).browser_steps) == 20
    with pytest.raises(ValidationError):
        monitor([text_field()], [{'type': 'text_changed', 'field': 'value'}],
                mode='browser', browser_steps=steps + steps[:1])


def test_item_field_acceptance_boundary():
    items = [{'name': f'i{index}', 'type': 'text', 'semantic': 'Item', 'path': 'id'}
             for index in range(32)]
    assert len(json_list_field(item_fields=items).item_fields) == 32
    with pytest.raises(ValidationError):
        json_list_field(item_fields=items + [items[0]])


def test_raw_json_rows_fail_before_any_item_normalization(monkeypatch):
    def unexpected(*args):
        raise AssertionError('an oversized raw row was normalized')

    monkeypatch.setattr(json_extraction, 'normalize_json_scalar', unexpected)
    body = {'rows': [{'id': 'same'}] * 200_000}
    with pytest.raises(DomainError) as failure:
        extract_json_field(body, json_list_field(), 'https://example.com/', 'items')
    assert failure.value.code == 'collection_limit'
    assert failure.value.details['limit'] == 'raw_list_items'


def test_field_max_items_precedes_json_and_html_row_normalization(monkeypatch):
    def unexpected(*args):
        raise AssertionError('a row beyond max_items was normalized')

    monkeypatch.setattr(json_extraction, 'normalize_json_scalar', unexpected)
    with pytest.raises(DomainError) as json_failure:
        extract_json_field({'rows': [{'id': 'a'}, {'id': 'b'}]},
                           json_list_field(max_items=1), 'https://example.com/', 'items')
    assert json_failure.value.details['reason'] == 'max_items'

    spec = monitor([{
        'name': 'items', 'type': 'list', 'semantic': 'Items', 'selector': '.row',
        'max_items': 1,
        'item_fields': [{'name': 'id', 'type': 'text', 'semantic': 'ID', 'selector': '.id'}],
    }], [{'type': 'list_added', 'field': 'items'}],
        business_key={'field': 'items', 'item_fields': ['id']})
    monkeypatch.setattr(html_extraction, '_scalar', unexpected)
    with pytest.raises(DomainError) as html_failure:
        html_extraction.extract_fields(
            '<div class="row"><b class="id">a</b></div>' * 2, spec,
            'https://example.com/')
    assert html_failure.value.details['reason'] == 'max_items'


@pytest.mark.asyncio
async def test_pagination_normalizes_only_remaining_rows_plus_one(monkeypatch):
    source = {'kind': 'json', 'steps': [
        {'id': 'data', 'request': {'url': 'https://api.example.com/items'}}],
        'pagination': {'kind': 'page', 'max_pages': 3, 'max_items': 3}}
    spec = monitor([{
        'name': 'items', 'type': 'list', 'semantic': 'Items', 'path': 'rows',
        'item_fields': [{'name': 'id', 'type': 'text', 'semantic': 'ID', 'path': 'id'}],
    }], [{'type': 'list_added', 'field': 'items'}], source=source,
        business_key={'field': 'items', 'item_fields': ['id']})
    calls = 0
    real_normalize = json_extraction.normalize_json_scalar

    def counted(*args):
        nonlocal calls
        calls += 1
        return real_normalize(*args)

    monkeypatch.setattr(json_extraction, 'normalize_json_scalar', counted)
    response = httpx.Response(
        200,
        headers={'content-type': 'application/json'},
        stream=httpx.ByteStream(json.dumps({
            'rows': [{'id': str(index)} for index in range(10)]
        }).encode()),
    )
    result = await api_collection.collect_api(
        spec.url, spec, transport=httpx.MockTransport(lambda request: response))
    assert [row['id'] for row in result.fields['items']] == ['0', '1', '2']
    assert calls == 4
    assert result.warnings == ['pagination_truncated']


def test_normalized_field_and_result_utf8_budgets(monkeypatch):
    monkeypatch.setattr(html_extraction, 'MAX_NORMALIZED_FIELD_BYTES', 32)
    scalar = FieldSpec.model_validate(text_field(path='value'))
    with pytest.raises(DomainError) as field_failure:
        extract_json_field({'value': 'é' * 40}, scalar, 'https://example.com/', 'value')
    assert field_failure.value.details['limit'] == 'normalized_field_bytes'

    monkeypatch.setattr(html_extraction, 'MAX_NORMALIZED_FIELD_BYTES', 1024)
    monkeypatch.setattr(html_extraction, 'MAX_NORMALIZED_RESULT_BYTES', 80)
    budget = NormalizedResultBudget()
    budget.add('first', 'x' * 40)
    with pytest.raises(DomainError) as result_failure:
        budget.add('other', 'y' * 40)
    assert result_failure.value.details['limit'] == 'normalized_result_bytes'
    assert result_failure.value.details['field'] == 'other'


def test_pathological_regexes_share_one_fail_closed_wall_clock_budget(monkeypatch):
    spec = monitor([text_field()], [
        {'type': 'regex_match', 'field': 'value', 'pattern': '(a+)+$'}
        for _ in range(4)])
    monkeypatch.setattr(rule_diff, 'REGEX_TIMEOUT_SECONDS', 0.01)
    monkeypatch.setattr(rule_diff, 'RULE_EVALUATION_TIMEOUT_SECONDS', 0.015)
    previous_state = {'predicates': {'0': False}, 'aggregate': False}
    with pytest.raises(DomainError) as failure:
        evaluate_rules(spec, {'value': 'before'}, {'value': 'a' * 100_000 + '!'},
                       previous_state)
    assert failure.value.code == 'rule_timeout'
    assert failure.value.details['reason'] == 'total_timeout'
    assert previous_state == {'predicates': {'0': False}, 'aggregate': False}


def scalar_json_spec():
    source = {'kind': 'json', 'steps': [
        {'id': 'data', 'request': {'url': 'https://api.example.com/value'}}]}
    return monitor([text_field(path='value')],
                   [{'type': 'text_changed', 'field': 'value'}], source=source)


@pytest.mark.asyncio
async def test_json_parsing_leaves_event_loop_responsive(monkeypatch):
    real_loads = json.loads
    loop_thread = threading.get_ident()
    parse_threads = []

    def slow_loads(value):
        parse_threads.append(threading.get_ident())
        time.sleep(0.05)
        return real_loads(value)

    monkeypatch.setattr(api_collection.json, 'loads', slow_loads)
    spec = scalar_json_spec()
    response = httpx.Response(200, headers={'content-type': 'application/json'},
                              stream=httpx.ByteStream(b'{"value":"ok"}'))
    task = asyncio.create_task(api_collection.collect_api(
        spec.url, spec, transport=httpx.MockTransport(lambda request: response)))
    await asyncio.sleep(0.01)
    assert not task.done(), 'the heartbeat was starved by synchronous JSON parsing'
    assert (await task).fields == {'value': 'ok'}
    assert parse_threads and parse_threads[0] != loop_thread


@pytest.mark.asyncio
async def test_html_extraction_leaves_event_loop_responsive(monkeypatch):
    async def fake_fetch(url, **kwargs):
        return FetchResult(url, 200, httpx.Headers({'content-type': 'text/html'}),
                           b'<p class="value">ok</p>')

    real_extract = http_collection.extract_fields
    loop_thread = threading.get_ident()
    extraction_threads = []

    def slow_extract(*args, **kwargs):
        extraction_threads.append(threading.get_ident())
        time.sleep(0.05)
        return real_extract(*args, **kwargs)

    monkeypatch.setattr(http_collection, 'fetch_bounded', fake_fetch)
    monkeypatch.setattr(http_collection, 'extract_fields', slow_extract)
    spec = monitor([text_field()], [{'type': 'text_changed', 'field': 'value'}])
    task = asyncio.create_task(http_collection.collect_http(spec.url, spec))
    await asyncio.sleep(0.01)
    assert not task.done(), 'the heartbeat was starved by synchronous HTML extraction'
    assert (await task).fields == {'value': 'ok'}
    assert extraction_threads and extraction_threads[0] != loop_thread
