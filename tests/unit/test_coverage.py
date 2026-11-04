from bs4 import BeautifulSoup

from webmonitor.collection.coverage import full_list_evidence, rows_complete
from webmonitor.collection.types import analyze_html, collection_coverage
from webmonitor.schemas.monitors import MonitorSpec


def test_declared_total_requires_every_unique_position():
    complete='<ul id="items"><li aria-setsize="2" aria-posinset="1">A</li><li aria-setsize="2" aria-posinset="2">B</li></ul>'
    assert rows_complete(BeautifulSoup(complete,'lxml').select('li'))
    assert full_list_evidence(complete)[0]['declared_total']==2
    partial='<ul><li aria-setsize="2" aria-posinset="1">A</li></ul>'
    assert not rows_complete(BeautifulSoup(partial,'lxml').select('li'))
    duplicate=complete.replace('aria-posinset="2"','aria-posinset="1"')
    assert not full_list_evidence(duplicate)
    unknown='<ul><li>A</li><li>B</li></ul>'
    assert not full_list_evidence(unknown)


def test_pagination_control_is_bounded_but_next_app_root_is_not_pagination():
    _,warnings=analyze_html('<div id="__next"><h1>Product</h1></div>')
    assert 'pagination_coverage_unproven' not in warnings
    _,warnings=analyze_html('<button id="next-page">Load next page</button>')
    assert 'pagination_coverage_unproven' in warnings


def test_bounded_deletion_is_marked_in_coverage():
    spec = MonitorSpec.model_validate({
        'name': 'Bounded deletion', 'url': 'https://example.com/products',
        'collection_mode': 'http',
        'fields': [{'name': 'products', 'type': 'list', 'semantic': 'Products',
                    'selector': '.row', 'allow_empty': True,
                    'item_fields': [{'name': 'id', 'type': 'text', 'semantic': 'ID',
                                     'selector': '.id'}]}],
        'business_key': {'field': 'products', 'item_fields': ['id']},
        'change_rules': {'mode': 'any',
                         'rules': [{'type': 'list_removed', 'field': 'products'}]},
        'coverage': {'scope': 'bounded', 'description': 'One page only'},
    })
    warnings = []
    coverage = collection_coverage(spec, warnings, html='<div class="row"><span class="id">A</span></div>')
    assert coverage['scope'] == 'bounded'
    assert 'deletion_coverage_bounded' in warnings
    assert 'observed rows' in coverage['description']
