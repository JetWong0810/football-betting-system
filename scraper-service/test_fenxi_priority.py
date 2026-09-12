"""缺亚盘优先; MySQL UTC 时间戳按 UTC 算年龄。"""
from datetime import datetime, timedelta, timezone

from scraper.sporttery_service import need_asian_fetch, need_form_fetch
from scraper.zgzcw_fenxi import FenxiSession


def test_missing_form_always_fetch():
    assert need_form_fetch(None) is True
    assert need_form_fetch({}) is True
    assert need_form_fetch({"form_len": 0, "form_fetched_at": datetime.utcnow()}) is True


def test_fresh_form_skip():
    assert need_form_fetch({
        "form_len": 800,
        "form_fetched_at": datetime.utcnow() - timedelta(hours=1),
    }) is False


def test_stale_form_fetch():
    assert need_form_fetch({
        "form_len": 800,
        "form_fetched_at": datetime.utcnow() - timedelta(hours=7),
    }) is True


def test_fresh_asian_skip():
    assert need_asian_fetch({
        "asian_len": 400,
        "asian_fetched_at": datetime.utcnow() - timedelta(minutes=10),
    }) is False


def test_stale_or_missing_asian_fetch():
    assert need_asian_fetch(None) is True
    assert need_asian_fetch({
        "asian_len": 400,
        "asian_fetched_at": datetime.utcnow() - timedelta(minutes=30),
    }) is True
    assert need_asian_fetch(
        {"asian_len": 400, "asian_fetched_at": datetime.utcnow()},
        force=True,
    ) is True


def test_mysql_utc_now_not_stale_under_cst():
    """生产: mysql NOW()=UTC, scraper datetime.now()=CST, 刚写入不能算过期。"""
    mysql_now = datetime.utcnow() - timedelta(minutes=5)
    assert need_form_fetch({
        "form_len": 800,
        "form_fetched_at": mysql_now,
    }) is False
    assert need_asian_fetch({
        "asian_len": 400,
        "asian_fetched_at": mysql_now,
    }) is False


def test_aware_utc_timestamp_not_stale():
    ts = datetime.now(timezone.utc) - timedelta(minutes=3)
    assert need_form_fetch({"form_len": 800, "form_fetched_at": ts}) is False


def test_single_block_does_not_abort_round():
    sess = FenxiSession(budget=5)
    assert sess._note_blocked("ypdb fid=1") is None
    assert sess.aborted is False
    assert sess.block_streak == 1


def test_consecutive_blocks_abort_round():
    sess = FenxiSession(budget=5)
    sess._note_blocked("ypdb fid=1")
    sess._note_blocked("ypdb fid=2")
    assert sess.aborted is True
    assert sess.block_streak == 2


if __name__ == "__main__":
    test_missing_form_always_fetch()
    test_fresh_form_skip()
    test_stale_form_fetch()
    test_fresh_asian_skip()
    test_stale_or_missing_asian_fetch()
    test_mysql_utc_now_not_stale_under_cst()
    test_aware_utc_timestamp_not_stale()
    test_single_block_does_not_abort_round()
    test_consecutive_blocks_abort_round()
    print("ok fenxi priority")
