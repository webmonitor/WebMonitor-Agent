"""Reject ambiguous extraction contracts before any preview or approval."""
import json
from datetime import UTC, datetime, timedelta, timezone
from decimal import Decimal
from uuid import uuid4

import pytest
from pydantic import ValidationError

from webmonitor.schemas.monitors import (
    DraftSpec,
    FieldSpec,
    Normalization,
    canonical_json,
    content_hash,
)


def field(kind, **options):
    return FieldSpec.model_validate({'name': 'value', 'type': kind, 'semantic': 'Extracted value',
                                    'selector': '.value', **options})


@pytest.mark.parametrize('kind,normalization', [
    ('number', {}), ('money', {'decimal_separator': '.'}),
    ('date', {'date_format': '%Y-%m-%d'}),
    ('boolean', {'true_values': ['yes'], 'false_values': []}),
    ('text', {'currency': 'USD'}),
])
def test_typed_fields_reject_missing_or_inapplicable_parse_configuration(kind, normalization):
    with pytest.raises(ValidationError):
        field(kind, normalize=normalization)


def test_ambiguous_decimal_and_boolean_maps_rejected():
    with pytest.raises(ValidationError):
        Normalization(decimal_separator=',', thousands_separator=',')
    with pytest.raises(ValidationError):
        Normalization(true_values=[' yes '], false_values=['yes'])
    with pytest.raises(ValidationError):
        Normalization(true_values=['a  b'], false_values=['a b'], collapse_whitespace=True)


@pytest.mark.parametrize('selector', ['//span', 'xpath=//span', 'javascript:alert(1)', 'div[', 'div::before'])
def test_non_css_or_non_element_selectors_are_rejected(selector):
    with pytest.raises(ValidationError):
        field('text', selector=selector)


def test_unknown_code_and_scalar_list_options_rejected():
    with pytest.raises(ValidationError):
        field('text', expression='document.cookie')
    with pytest.raises(ValidationError):
        field('text', min_items=1)
    with pytest.raises(ValidationError):
        field('list', item_fields=[{'name': 'id', 'type': 'text', 'semantic': 'ID', 'selector': '.id'}],
              min_items=2, max_items=1)


def test_canonical_hash_normalizes_timezone_and_object_order():
    utc = datetime(2026, 10, 2, 12, tzinfo=UTC)
    offset = utc.astimezone(timezone(timedelta(hours=8)))
    first = {'at': utc, 'value': Decimal('12.50')}
    second = {'value': Decimal('12.50'), 'at': offset}
    assert content_hash(first) == content_hash(second)
    assert json.loads(canonical_json(first)) == {'at': '2026-10-02T12:00:00Z', 'value': '12.50'}
    assert content_hash(first) != content_hash({'at': utc, 'value': Decimal('13.50')})
    with pytest.raises(ValueError):
        canonical_json({'at': utc.replace(tzinfo=None)})


def json_source_spec(**overrides):
    data = {
        'name': 'API monitor', 'url': 'https://page.example.com/list',
        'collection_mode': 'http',
        'source': {'kind': 'json',
                   'steps': [{'id': 'data',
                              'request': {'url': 'https://api.example.com/items'}}]},
        'fields': [{'name': 'items', 'type': 'list', 'semantic': 'Items',
                    'path': 'data.list',
                    'item_fields': [{'name': 'id', 'type': 'text', 'semantic': 'ID',
                                     'path': 'id'}]}],
        'business_key': {'field': 'items', 'item_fields': ['id']},
        'change_rules': {'mode': 'any', 'rules': [{'type': 'list_added', 'field': 'items'}]},
        'schedule': {'interval_seconds': 60, 'timezone': 'UTC'},
        'notification_group_ids': [str(uuid4())],
        'coverage': {'scope': 'full', 'description': 'Visible rows'},
    }
    data.update(overrides)
    return data


def path_field(path='data.list'):
    return {'name': 'items', 'type': 'list', 'semantic': 'Items', 'path': path,
            'item_fields': [{'name': 'id', 'type': 'text', 'semantic': 'ID', 'path': 'id'}]}


def test_json_paths_are_normalized_and_exclusive():
    assert FieldSpec.model_validate({'name': 'value', 'type': 'text', 'semantic': 'Value',
                                     'path': '$.data.title'}).path == 'data.title'
    # Selector-only fields remain valid, so existing HTML specs are unchanged.
    assert field('text').selector == '.value'
    for options in ({'selector': '.value', 'path': 'data.title'}, {}):
        with pytest.raises(ValidationError):
            FieldSpec.model_validate({'name': 'value', 'type': 'text', 'semantic': 'Value',
                                      **options})
    with pytest.raises(ValidationError):
        FieldSpec.model_validate({'name': 'value', 'type': 'text', 'semantic': 'Value',
                                  'path': 'data.title', 'attribute': 'href'})
    for path in ('', 'data..title', 'data[*]', '$.', '$..title', 'data['):
        with pytest.raises(ValidationError):
            FieldSpec.model_validate({'name': 'value', 'type': 'text', 'semantic': 'Value',
                                      'path': path})


def test_json_sources_require_http_mode_without_browser_steps():
    with pytest.raises(ValidationError):
        DraftSpec.model_validate(json_source_spec(collection_mode='browser'))
    with pytest.raises(ValidationError):
        DraftSpec.model_validate(json_source_spec(
            browser_steps=[{'type': 'scroll', 'max_steps': 1}]))


def test_one_channel_per_spec():
    selector_field = {'name': 'items', 'type': 'list', 'semantic': 'Items',
                      'selector': '.row',
                      'item_fields': [{'name': 'id', 'type': 'text', 'semantic': 'ID',
                                       'selector': '.id'}]}
    with pytest.raises(ValidationError):
        DraftSpec.model_validate(json_source_spec(fields=[selector_field]))
    with pytest.raises(ValidationError):
        DraftSpec.model_validate(json_source_spec(source=None, fields=[path_field()]))


def test_source_steps_are_ordered_and_unique():
    later = {'kind': 'json', 'steps': [
        {'id': 'first', 'request': {'url': 'https://api.example.com/{{steps.second.id}}'}},
        {'id': 'second', 'request': {'url': 'https://api.example.com/second'}},
    ]}
    with pytest.raises(ValidationError):
        DraftSpec.model_validate(json_source_spec(source=later))
    unknown = {'kind': 'json', 'steps': [
        {'id': 'first', 'request': {'url': 'https://api.example.com/{{steps.missing.id}}'}},
    ]}
    with pytest.raises(ValidationError):
        DraftSpec.model_validate(json_source_spec(source=unknown))
    duplicate = {'kind': 'json', 'steps': [
        {'id': 'first', 'request': {'url': 'https://api.example.com/one'}},
        {'id': 'first', 'request': {'url': 'https://api.example.com/two'}},
    ]}
    with pytest.raises(ValidationError):
        DraftSpec.model_validate(json_source_spec(source=duplicate))


def test_request_headers_and_bodies_follow_the_replay_contract():
    def single(request):
        return {'kind': 'json', 'steps': [{'id': 'first', 'request': request}]}

    for request in (
        {'url': 'https://api.example.com/items', 'headers': {'Cookie': 'session=1'}},
        {'url': 'https://api.example.com/items', 'headers': {'User-Agent': 'a\r\nX: b'}},
        {'method': 'GET', 'url': 'https://api.example.com/items', 'body': {'q': 1}},
        {'method': 'POST', 'url': 'https://api.example.com/items', 'body': 'text'},
        {'method': 'POST', 'url': 'https://api.example.com/items', 'body': {'q': '{{steps.x}}'}},
    ):
        with pytest.raises(ValidationError):
            DraftSpec.model_validate(json_source_spec(source=single(request)))
    accepted = DraftSpec.model_validate(json_source_spec(source=single(
        {'method': 'POST', 'url': 'https://api.example.com/items',
         'headers': {'Accept-Language': 'zh-CN'}, 'body': {'query': 'x'}})))
    assert accepted.source.steps[0].request.headers == {'accept-language': 'zh-CN'}


def test_request_url_keeps_templates_out_of_the_host():
    with pytest.raises(ValidationError):
        DraftSpec.model_validate(json_source_spec(source={'kind': 'json', 'steps': [
            {'id': 'first', 'request': {'url': 'https://{{steps.missing.host}}/items'}}]}))
    accepted = DraftSpec.model_validate(json_source_spec(source={'kind': 'json', 'steps': [
        {'id': 'info', 'request': {'url': 'https://api.example.com/info'}},
        {'id': 'items', 'request': {'url': 'https://api.example.com/items/{{steps.info.data.id}}'}}]}))
    assert accepted.source.steps[1].request.url.endswith('{{steps.info.data.id}}')


def test_page_pagination_requires_one_list_and_complete_configuration():
    second_list = {'name': 'other', 'type': 'list', 'semantic': 'Other', 'path': 'data.other',
                   'item_fields': [{'name': 'id', 'type': 'text', 'semantic': 'ID', 'path': 'id'}]}
    base = json_source_spec()
    with pytest.raises(ValidationError):
        DraftSpec.model_validate({**base, 'fields': [path_field(), second_list],
                                  'source': {**base['source'],
                                             'pagination': {'kind': 'page'}}})
    for pagination in ({'kind': 'page', 'size_param': 'limit'},
                       {'kind': 'page', 'stop': 'total_reached'},
                       {'kind': 'page', 'size': 10}):
        with pytest.raises(ValidationError):
            DraftSpec.model_validate({**base, 'source': {
                **base['source'], 'pagination': pagination}})
    accepted = DraftSpec.model_validate({**base, 'source': {
        **base['source'],
        'pagination': {'kind': 'page', 'size_param': 'limit', 'size': 10}}})
    assert accepted.source.pagination.max_pages == 3
