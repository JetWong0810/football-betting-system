"""聊天: 自动刷新触发条件 / 总结规则 / 盘口读法。mock 掉抓取与模型, 不联网。"""
from datetime import datetime

import odds500_live as L
from match_chat import context as C
from match_chat import service as S
from match_chat.context import ah_reading, freshness_text, ou_reading


def _run(text, fr, refreshed):
    cap = {}
    S.stream_chat = lambda system, messages, web=True: (cap.update(system=system) or iter(
        [{"type": "delta", "text": "ok"}, {"type": "sources", "items": []}, {"type": "usage", "usage": {}}]))
    import match_chat.context as ctxm
    ctxm.market_freshness = lambda mid, now=None: fr
    L.refresh_match_odds = lambda mid, force=False: refreshed.append(1) or {"ok": True, "fetchedAt": "2026-11-24 12:30:00", "got": 15, "failed": [], "ticks": 3}
    ev = list(S.run_turn(1, "2042949", text, [], web=False, persist=False))
    return cap["system"], [e.get("text") for e in ev if e["type"] == "status"]


def _fr(eta, age):
    return {"now": datetime(2026, 11, 24, 12, 0), "eta": eta, "ageMin": age, "lastFetch": datetime(2026, 11, 24, 11, 0), "lastChange": None}


def test_auto_refresh_when_stale_and_near():
    n = []
    sysm, st = _run("请关联本场盘口和赔率数据分析", _fr(1800, 31), n)
    assert n and any("自动抓取" in (x or "") for x in st) and "本次实时抓取" in sysm


def test_no_auto_refresh_when_fresh_far_or_started():
    for fr in (_fr(1800, 3), _fr(6 * 3600, 60), _fr(-600, 60), _fr(None, None)):
        n = []
        _run("请关联本场盘口和赔率数据分析", fr, n)
        assert not n, fr


def test_no_auto_refresh_without_odds_request():
    n = []
    _run("首发出来了吗", _fr(1800, 60), n)
    assert not n


def test_summary_note():
    sysm, _ = _run("把上面的分析总结成三句话,给出最终倾向", _fr(None, None), [])
    assert "总结/结论类请求" in sysm
    sysm2, _ = _run("为什么进球多", _fr(None, None), [])
    assert "总结/结论类请求" not in sysm2


def test_readings_and_freshness_text():
    t = ah_reading(0.25, "布伦特", "埃弗顿")
    assert "平局→布伦特输半/埃弗顿赢半" in t and "上盘=让球方(布伦特)" in t
    assert "平局→A全赢/B全输" in ah_reading(-0.75, "A", "B")
    assert "总进球3→大球赢半/小球输半" in ou_reading(2.75)
    s = freshness_text(_fr(1500, 40))
    assert "滞后 40 分钟" in s and "不得断言" in s
    assert "滞后" not in freshness_text(_fr(1500, 4))
    assert "滞后" not in freshness_text(_fr(-100, 400))


if __name__ == "__main__":
    for n, f in list(globals().items()):
        if n.startswith("test_"):
            f(); print("ok", n)
