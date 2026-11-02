"""The first message names a conversation only until the model names it."""
from webmonitor.agent.titling import (
    clean_generated_title,
    needs_generated_title,
    provisional_title,
)


def test_provisional_title_is_one_bounded_line():
    assert provisional_title("  监控\n清华史苑   更新  ") == "监控 清华史苑 更新"
    assert provisional_title("监控价格，") == "监控价格"
    long = "字" * 80
    title = provisional_title(long)
    assert title is not None and title.endswith("…")
    assert len(title) <= 61


def test_generated_title_drops_model_packaging():
    assert clean_generated_title("“标题：清华史苑更新。”") == "清华史苑更新"
    assert clean_generated_title("Title: Tsinghua news updates.") == "Tsinghua news updates"
    assert clean_generated_title("  \n ") is None
    assert clean_generated_title(None) is None


def test_generated_title_is_bounded():
    assert len(clean_generated_title("题" * 90) or "") == 40


def test_only_missing_or_placeholder_titles_are_replaced():
    message = "监控清华史苑的文章更新"
    assert needs_generated_title(None, message)
    assert needs_generated_title(provisional_title(message), message)
    assert not needs_generated_title("清华史苑文章更新", message)
