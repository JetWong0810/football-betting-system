"""500.com 逐次变动: 解析 / 年份推断 / 开赛后剔除 / 熔断与空响应重试 / 调度。纯本地, 不联网。"""
import json
import os
import time
from datetime import datetime

import httpx

from scraper import odds500_ticks as T
from scraper import sporttery_service as S

FIX = os.path.join(os.path.dirname(__file__), "fixtures")
KO = datetime(2026, 11, 24, 15, 45)


def _load(name):
    with open(os.path.join(FIX, name), "rb") as f:
        return json.loads(f.read().decode("utf-8"))


def test_parse_ah_text():
    assert T.parse_ah_text("受球半") == (-1.5, "受球半")
    assert T.parse_ah_text("半球") == (0.5, "半球")
    assert T.parse_ah_text("平手/半球")[0] == 0.25
    assert T.parse_ah_text("受一球/球半")[0] == -1.25
    assert T.parse_ah_text("")[0] is None


def test_parse_ou_line():
    assert T.parse_ou_line("2.5") == 2.5
    assert T.parse_ou_line("3.5/4") == 3.75
    assert T.parse_ou_line("2/2.5") == 2.25
    assert T.parse_ou_line("abc") is None


def test_infer_year_and_cross_year():
    assert T.infer_tick_dt("11-24 12:06", KO) == datetime(2026, 11, 24, 12, 6)
    # 跨年: 1 月开赛, 12 月的初盘记录应归到上一年
    assert T.infer_tick_dt("12-30 10:00", datetime(2027, 1, 2, 20, 0)) == datetime(2026, 12, 30, 10, 0)
    assert T.infer_tick_dt("2026-11-24 11:53:37", KO) == datetime(2026, 11, 24, 11, 53, 37)
    assert T.infer_tick_dt("垃圾", KO) is None


def test_parse_fixtures_real_samples():
    ah = T.parse_asian_history(_load("o500_ah_5.json"), KO)
    assert ah and all(r["handicap"] is not None and r["time"] <= KO for r in ah)
    assert ah[0]["time"] >= ah[-1]["time"]                      # 新→旧
    ou = T.parse_ou_history(_load("o500_ou_5.json"), KO)
    assert ou and any(r["line"] == 3.75 for r in ou)            # 3.5/4 -> 3.75
    eu = T.parse_euro_history(_load("o500_euro_122.json"), KO)
    assert eu and eu[0]["win"] > 1 and eu[0]["time"].second >= 0


def test_drop_after_kickoff():
    rows = [{"time": datetime(2026, 11, 24, 15, 40)}, {"time": datetime(2026, 11, 24, 15, 50)}]
    assert len(T.drop_after_kickoff(rows, KO)) == 1


def test_fid_list_parse():
    with open(os.path.join(FIX, "o500_list.html"), "rb") as f:
        m = T.parse_fid_list(f.read().decode("gbk", "replace"), 2026)
    assert m["周二001"]["fid"] == "1474022" and m["周二001"]["kickoff"] == KO


def _client(handler):
    c = T.Odds500Client(gap_min=0, gap_max=0)
    c._client = httpx.Client(transport=httpx.MockTransport(handler), headers=T.HEADERS)
    return c


def test_empty_body_retries_once_then_empty(monkeypatch=None):
    T.reset_state()
    calls = []
    real_sleep = time.sleep
    time.sleep = lambda s: None
    try:
        def h(req):
            calls.append(1)
            return httpx.Response(200, content=b"\n\n\n")
        with _client(h) as c:
            assert c.fetch_history("asian", "1", 3, KO) == []      # 空 != 失败, 不触发熔断
            assert len(calls) == 2 and c.allow()
    finally:
        time.sleep = real_sleep


def test_567_trips_breaker_and_blocks_further_requests():
    T.reset_state()
    n = []
    def h(req):
        n.append(1)
        return httpx.Response(567, content=b"x")
    with _client(h) as c:
        assert c.fetch_history("ou", "1", 3, KO) is None
        assert not c.allow() and T.breaker_open()
        assert c.fetch_history("ou", "1", 5, KO) is None
        assert len(n) == 1                                          # 熔断后不再发请求
    T.reset_state()


def test_html_instead_of_json_trips():
    T.reset_state()
    with _client(lambda r: httpx.Response(200, content=b"<html>shield</html>")) as c:
        assert c.fetch_history("euro", "1", 3, KO) is None
        assert T.breaker_open()
    T.reset_state()


def test_o500_tasks_and_cover():
    now = time.time()
    F = {}
    assert S.due_o500_tasks("m", 20000, now, F, set()) == []
    assert len(S.due_o500_tasks("m", 7200, now, F, set())) == 12      # 精简集合 4 家 × 3 类
    assert len(S.due_o500_tasks("m", 3000, now, F, set())) == 21      # 核心 7 家 × 3 类
    for k in ("asian", "ou", "euro"):
        for c in (3, 280, 1055):
            F[("m", k, c)] = now - 60
    assert S.o500_covered("m", now, F)
    assert len(S.due_o500_tasks("m", 7200, now, F, set())) == 3       # 只剩香港马会三类(精简集合中)
    assert S.due_o500_tasks("m", -60, now, F, {"m"}) == []


if __name__ == "__main__":
    for n, f in list(globals().items()):
        if n.startswith("test_"):
            f()
            print("ok", n)
