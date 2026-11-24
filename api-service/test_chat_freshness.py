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


def _fr(eta, age, ou_age=None):
    lf = datetime(2026, 11, 24, 11, 0)
    ka = {"lastFetch": lf if age is not None else None, "ageMin": age}
    ko = {"lastFetch": lf if (ou_age if ou_age is not None else age) is not None else None, "ageMin": ou_age if ou_age is not None else age}
    return {"now": datetime(2026, 11, 24, 12, 0), "eta": eta, "ageMin": max([x for x in (age, ou_age) if x is not None] or [None]) if age is not None else None,
            "lastFetch": lf, "lastChange": None, "kinds": {"asian": ka, "ou": ko, "euro": ka}}


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
    assert "已滞后" in s and "不得断言" in s and "40 分钟前" in s
    assert "已滞后" not in freshness_text(_fr(1500, 4))
    assert "已滞后" not in freshness_text(_fr(-100, 400))
    # 分项: 亚盘/欧赔很新, 只有大小球旧 -> 注意里只点名大小球(大小球曾被亚盘的新鲜度掩盖)
    s2 = freshness_text(_fr(1500, 2, ou_age=45))
    assert "大小球的数据已滞后" in s2 and "亚盘、" not in s2.split("【注意】")[1].split("的数据已滞后")[0]


if __name__ == "__main__":
    for n, f in list(globals().items()):
        if n.startswith("test_"):
            f(); print("ok", n)


def test_split_sections_keeps_all_market_blocks():
    """回归: 【其他公司逐次变动】【水位参考】曾因标题未登记被丢弃, 模型根本看不到。"""
    text = "【比赛】\nx\n【盘口】a\n数据新鲜度: x\n【盘口读法】r\n【水位参考·亚盘】w\n【欧赔】e\n【大小球】o\n【其他公司逐次变动】(t)\n香港马会 亚盘 逐次变动\n- p\n【主队近期战绩】f\n"
    secs = C.split_sections(text)
    for k in ("数据新鲜度", "盘口读法", "水位参考·亚盘", "其他公司逐次变动", "香港马会 亚盘 逐次变动"):
        assert k in secs["odds"], k
    assert "主队近期战绩" in secs["recent"] and "水位参考" not in secs["recent"]


def test_breakeven_text():
    assert "58%→0.72" in C.breakeven_text("主水", 0.95, "客水", 0.9) and "主水0.95(需有效胜率≥51.3%)" in C.breakeven_text("主水", 0.95, "客水", 0.9)


def test_overlay_500_prefers_fresh_500_and_adds_hkjc():
    import zgzcw_cache as Z
    real = Z.list_o500_ticks
    rows = {("overunder", "Bet365"): [{"over": 0.9, "line": 3.0, "under": 0.95, "time": "2026-11-24 18:01:00"},
                                      {"over": 0.8, "line": 2.75, "under": 1.0, "time": "2026-11-23 12:00:00"}],
            ("overunder", "香港马会"): [{"over": 0.7, "line": 2.75, "under": 1.05, "time": "2026-11-24 17:21:00"}]}
    Z.list_o500_ticks = lambda kind, mid, name: rows.get((kind, name), [])
    try:
        cache = [{"bookmaker": "Bet365", "cid": 2, "initial": {"line": 2.75}, "current": {"line": 2.75, "over": 0.82}},
                 {"bookmaker": "立博", "cid": 5, "initial": {"line": 2.5}, "current": {"line": 2.5}}]
        out, used = C.overlay_500("m", "ou", cache)
        by = {x["bookmaker"]: x for x in out}
        assert used == 2 and by["Bet365"]["current"]["line"] == 3.0 and by["Bet365"]["initial"]["line"] == 2.75 and by["Bet365"]["cid"] == 2
        assert "香港马会" in by and by["香港马会"]["src500"] and by["立博"]["current"]["line"] == 2.5 and not by["立博"].get("src500")
    finally:
        Z.list_o500_ticks = real


def test_odd_open_flag():
    assert "水位失衡" in C._odd_open("ou", {"over": 1.3, "under": 0.57}) and C._odd_open("ou", {"over": 0.9, "under": 0.95}) == ""
