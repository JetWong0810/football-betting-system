"""API-Football 映射规则测试(纯函数, 不联网不连库)。python3 test_af_mapping.py"""
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
from api_football.mapping import pick  # noqa: E402

TS = 1_800_000_000


def fx(fid, h, a, ts=TS, league=("England", "Premier League", 39)):
    return {"fixture": {"id": fid, "timestamp": ts},
            "league": {"country": league[0], "name": league[1], "id": league[2]},
            "teams": {"home": {"id": fid * 10 + 1, "name": h}, "away": {"id": fid * 10 + 2, "name": a}}}


def m(h, a, league="英超"):
    return {"match_id": "x", "match_code": "c", "h": h, "a": a, "ts": TS, "league_name": league}


ALIAS = {"切尔西": "chelsea", "阿森纳": "arsenal"}


def test_both():
    r = pick(m("切尔西", "阿森纳"), [fx(1, "Chelsea", "Arsenal"), fx(2, "Liverpool", "Everton")], {}, ALIAS)
    assert r["method"] == "both" and r["fixture"]["fixture"]["id"] == 1


def test_one_side_learns_other():
    r = pick(m("切尔西", "某某队"), [fx(1, "Chelsea", "Foo FC"), fx(2, "Liverpool", "Everton")], {}, ALIAS)
    assert r["method"] == "one_side" and "某某队" in [c for c, _ in r["learn"]]


def test_one_side_ambiguous_rejected():
    r = pick(m("切尔西", "某某队"), [fx(1, "Chelsea", "Foo FC"), fx(2, "Chelsea", "Bar FC")], {}, ALIAS)
    assert r is None


def test_wrong_other_side_rejected():
    # 阿森纳有别名但候选客队是 Everton: 有线索却对不上, 不能当作"没信息"
    r = pick(m("切尔西", "阿森纳"), [fx(1, "Chelsea", "Everton")], {}, ALIAS)
    assert r is None


def test_learned_map_is_exact():
    tmap = {"某某队": (12, "Foo FC")}
    r = pick(m("切尔西", "某某队"), [fx(1, "Chelsea", "Foo FC")], tmap, ALIAS)
    assert r["method"] == "both"
    r = pick(m("切尔西", "某某队"), [fx(5, "Chelsea", "Other FC")], tmap, ALIAS)
    assert r is None


def test_time_window():
    assert pick(m("切尔西", "阿森纳"), [fx(1, "Chelsea", "Arsenal", ts=TS + 3600)], {}, ALIAS) is None


def test_league_unique_and_taken():
    mm = m("甲队", "乙队")
    f1, f2 = fx(1, "Alpha", "Beta"), fx(2, "Gamma", "Delta", league=("Spain", "La Liga", 140))
    assert pick(mm, [f1, f2], {}, ALIAS)["method"] == "league_unique"
    assert pick(mm, [f1, fx(3, "Eps", "Zeta")], {}, ALIAS) is None            # 同联赛两场 -> 不猜
    mm["_taken"] = {3}
    assert pick(mm, [f1, fx(3, "Eps", "Zeta")], {}, ALIAS)["fixture"]["fixture"]["id"] == 1


if __name__ == "__main__":
    for k, v in list(globals().items()):
        if k.startswith("test_"):
            v()
            print("ok", k)
