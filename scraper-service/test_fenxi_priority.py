"""缺基本面优先、亚盘已新跳过 ypdb。"""
from datetime import datetime, timedelta

from scraper.sporttery_service import need_asian_fetch, need_form_fetch


def test_missing_form_always_fetch():
    assert need_form_fetch(None) is True
    assert need_form_fetch({}) is True
    assert need_form_fetch({"form_len": 0, "form_fetched_at": datetime.now()}) is True


def test_fresh_form_skip():
    assert need_form_fetch({
        "form_len": 800,
        "form_fetched_at": datetime.now() - timedelta(hours=1),
    }) is False


def test_stale_form_fetch():
    assert need_form_fetch({
        "form_len": 800,
        "form_fetched_at": datetime.now() - timedelta(hours=7),
    }) is True


def test_fresh_asian_skip():
    assert need_asian_fetch({
        "asian_len": 400,
        "asian_fetched_at": datetime.now() - timedelta(minutes=10),
    }) is False


def test_stale_or_missing_asian_fetch():
    assert need_asian_fetch(None) is True
    assert need_asian_fetch({
        "asian_len": 400,
        "asian_fetched_at": datetime.now() - timedelta(minutes=30),
    }) is True
    assert need_asian_fetch(
        {"asian_len": 400, "asian_fetched_at": datetime.now()},
        force=True,
    ) is True
