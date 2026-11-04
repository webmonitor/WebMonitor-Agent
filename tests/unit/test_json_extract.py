"""JSON values follow the same normalization contract as extracted HTML text."""

import pytest

from webmonitor.collection.extraction import MISSING, normalize_json_scalar
from webmonitor.collection.json_extract import extract_json_field, resolve_path
from webmonitor.collection.validation import validate_collection
from webmonitor.errors import DomainError
from webmonitor.schemas.monitors import MonitorSpec, FieldSpec


def field(kind, name='value', path='value', **options):
    return FieldSpec.model_validate({'name': name, 'type': kind, 'semantic': 'Value',
                                     'path': path, **options})


def rejected(call, reason):
    with pytest.raises(DomainError) as error:
        call()
    assert error.value.code == 'collection_invalid'
    assert error.value.details['reason'] == reason


def json_spec(*fields, coverage='full'):
    return MonitorSpec.model_validate({
        'name': 'JSON monitor', 'url': 'https://page.example.com/list',
        'collection_mode': 'http',
        'source': {'kind': 'json',
                   'steps': [{'id': 'data',
                              'request': {'url': 'https://api.example.com/items'}}]},
        'fields': list(fields),
        'business_key': {'field': 'items', 'item_fields': ['id']},
        'change_rules': {'mode': 'any', 'rules': [{'type': 'list_added', 'field': 'items'}]},
        'coverage': {'scope': coverage, 'description': 'Rows'},
    })


LIST = {'name': 'items', 'type': 'list', 'semantic': 'Rows', 'path': 'data.list',
        'item_fields': [{'name': 'id', 'type': 'text', 'semantic': 'ID', 'path': 'id'}]}


def test_text_accepts_native_json_scalars():
    spec = field('text')
    assert normalize_json_scalar(' Name ', spec, 'https://e.com/', 'v') == 'Name'
    assert normalize_json_scalar(200, spec, 'https://e.com/', 'v') == '200'
    assert normalize_json_scalar(1.5, spec, 'https://e.com/', 'v') == '1.5'
    assert normalize_json_scalar(True, spec, 'https://e.com/', 'v') == 'true'
    assert normalize_json_scalar(False, spec, 'https://e.com/', 'v') == 'false'
    rejected(lambda: normalize_json_scalar({'a': 1}, spec, 'https://e.com/', 'v'), 'invalid_text')


def test_numbers_money_dates_and_booleans_keep_their_contracts():
    number = field('number', normalize={'decimal_separator': '.'})
    assert normalize_json_scalar(12, number, 'https://e.com/', 'v') == '12'
    assert normalize_json_scalar(12.5, number, 'https://e.com/', 'v') == '12.5'
    rejected(lambda: normalize_json_scalar('1,5', number, 'https://e.com/', 'v'),
             'invalid_number')
    money = field('money', normalize={'decimal_separator': '.', 'currency': 'CNY'})
    assert normalize_json_scalar(12.5, money, 'https://e.com/', 'v') == {
        'amount': '12.5', 'currency': 'CNY'}
    date = field('date', normalize={'date_format': '%Y-%m-%d %H:%M:%S', 'timezone': 'Asia/Shanghai'})
    assert normalize_json_scalar('2026-01-02 03:04:05', date, 'https://e.com/', 'v') == \
        '2026-01-01T19:04:05Z'
    rejected(lambda: normalize_json_scalar(1767, date, 'https://e.com/', 'v'), 'invalid_date')
    boolean = field('boolean', normalize={'true_values': ['1'], 'false_values': ['0']})
    assert normalize_json_scalar(True, boolean, 'https://e.com/', 'v') is True
    assert normalize_json_scalar(1, boolean, 'https://e.com/', 'v') is True
    assert normalize_json_scalar('0', boolean, 'https://e.com/', 'v') is False
    rejected(lambda: normalize_json_scalar('yes', boolean, 'https://e.com/', 'v'),
             'invalid_boolean')


def test_missing_and_empty_values_follow_required():
    assert normalize_json_scalar(None, field('text', required=False), 'https://e.com/', 'v') is MISSING
    rejected(lambda: normalize_json_scalar(None, field('text'), 'https://e.com/', 'v'),
             'required_missing')
    rejected(lambda: normalize_json_scalar('  ', field('text'), 'https://e.com/', 'v'),
             'required_empty')


def test_paths_walk_keys_and_indices():
    body = {'data': {'list': [{'id': 'a'}, {'id': 'b'}], 'total': 2}}
    assert resolve_path(body, 'data.list[1].id') == 'b'
    assert resolve_path(body, 'data.total') == 2
    with pytest.raises(IndexError):
        resolve_path(body, 'data.list[5]')
    with pytest.raises(KeyError):
        resolve_path(body, 'data.missing')


def test_list_rows_keep_required_and_optional_item_values():
    rows = field('list', name='items', path='data.list', item_fields=[
        {'name': 'id', 'type': 'text', 'semantic': 'ID', 'path': 'id'},
        {'name': 'note', 'type': 'text', 'semantic': 'Note', 'path': 'note', 'required': False},
    ])
    body = {'data': {'list': [{'id': 1, 'note': None}, {'id': 2, 'note': 'kept'}]}}
    assert extract_json_field(body, rows, 'https://e.com/', 'items') == [
        {'id': '1'}, {'id': '2', 'note': 'kept'}]
    rejected(lambda: extract_json_field({'data': {'list': [{}]}}, rows, 'https://e.com/', 'items'),
             'required_missing')
    rejected(lambda: extract_json_field({'data': {'list': ['row']}}, rows, 'https://e.com/',
                                        'items'), 'invalid_row')
    rejected(lambda: extract_json_field({'data': {'list': {}}}, rows, 'https://e.com/', 'items'),
             'invalid_list')


def test_business_keys_stay_unique_across_json_rows():
    spec = json_spec(LIST)
    rows = [{'id': 'a'}, {'id': 'a'}]
    with pytest.raises(DomainError) as error:
        validate_collection(spec, {'items': rows}, coverage=spec.coverage.model_dump())
    assert error.value.details['reason'] == 'duplicate_business_key'
    validate_collection(spec, {'items': [{'id': 'a'}, {'id': 'b'}]},
                        coverage=spec.coverage.model_dump())


def test_unknown_json_path_is_reported_as_missing():
    spec = field('text', path='data.missing')
    rejected(lambda: extract_json_field({'data': {}}, spec, 'https://e.com/', 'value'),
             'required_missing')
    assert extract_json_field({'data': {}}, field('text', path='data.missing', required=False),
                              'https://e.com/', 'value') is MISSING


def test_null_list_is_invalid_when_required_and_absent_otherwise():
    required = field('list', name='items', path='data.list', item_fields=[
        {'name': 'id', 'type': 'text', 'semantic': 'ID', 'path': 'id'}])
    rejected(lambda: extract_json_field({'data': {'list': None}}, required,
                                        'https://e.com/', 'items'), 'invalid_null')
    optional = field('list', name='items', path='data.list', required=False, item_fields=[
        {'name': 'id', 'type': 'text', 'semantic': 'ID', 'path': 'id'}])
    assert extract_json_field({'data': {'list': None}}, optional,
                              'https://e.com/', 'items') is MISSING
