"""裁判历史档案的纯函数测试(不联网不连库)。python3 test_af_referee_profile.py"""
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
from api_football.referee_profile import (aggregate, competitions, match_record, parse_name, ref_key, render_profile,  # noqa: E402
                                          same_person, same_surname_other_person, team_record, verdict, zscore)


def P(s):
    return parse_name(s)


def test_name_matching_variants_and_brothers():
    madley = P("Andrew Madley")
    assert same_person(madley, P("A. Madley")) and same_person(madley, P("Andy Madley, England")) and same_person(madley, P("Andrew Madley"))
    # 同姓不同人: 英冠的 Robert/Bobby Madley 不能算进英超 Andrew Madley
    assert not same_person(madley, P("Robert Madley, England")) and not same_person(madley, P("Bobby Madley")) and not same_person(madley, P("R. Madley"))
    assert same_surname_other_person(madley, P("Bobby Madley")) and not same_surname_other_person(madley, P("A. Madley"))
    # 昵称还原: Bobby=Robert, 所以这两种写法是同一个人
    assert same_person(P("Bobby Madley"), P("Robert Madley, England")) and same_person(P("Bobby Madley"), P("R. Madley"))
    # 多个姓: 全名和缩写互相包含
    assert same_person(P("Miguel Sesma Espinosa"), P("M. Sesma")) and same_person(P("Jesús Gil Manzano"), P("J. Gil Manzano"))
    assert same_person(P("Felix Zwayer, Germany"), P("F. Zwayer")) and same_person(P("Clément Turpin"), P("C. Turpin"))   # 重音
    assert not same_person(P("Felix Zwayer"), P("Daniel Siebert")) and not same_person(None, P("A. B"))


def test_ref_key_stable():
    assert ref_key("Andy Madley, England") == ref_key("A. Madley") == ref_key("Andrew Madley")
    assert ref_key("Bobby Madley") == ref_key("Robert Madley, England") != ref_key("A. Madley")
    assert ref_key("") is None and ref_key(None) is None


def parsed(fid, hid, aid, hg, ag, events, ts=1700000000, lg=39, season=2026):
    return {"match": {"fixture_id": fid, "league_id": lg, "season": season, "ts": ts, "home_id": hid, "away_id": aid, "hg": hg, "ag": ag, "status": "FT"},
            "events": [dict({"minute": 30, "extra": 0}, **e) for e in events]}


def ev(team, typ, detail):
    return {"team_id": team, "type": typ, "detail": detail}


def test_shootout_kicks_not_counted_as_penalties():
    from api_football.referee_profile import is_shootout_event
    assert is_shootout_event("PEN", 120, 3) and not is_shootout_event("PEN", 120, 0) and not is_shootout_event("AET", 120, 1) and not is_shootout_event("PEN", 87, 0)
    events = [ev(10, "Goal", "Penalty")] + [{"team_id": 10 if i % 2 else 20, "type": "Goal", "detail": "Penalty" if i % 3 else "Missed Penalty", "minute": 120, "extra": i + 1} for i in range(8)]
    for e in events[:1]:
        e.update({"minute": 55, "extra": 0})
    p = parsed(1, 10, 20, 1, 1, events)
    p["match"]["status"] = "PEN"
    r = match_record(p)
    assert (r["ph"], r["pa"]) == (1, 0)                       # 只有第 55 分钟那个真判罚的点球, 点球大战的 8 脚被排除
    p2 = parsed(2, 10, 20, 1, 1, [dict(events[1], extra=1)])
    p2["match"]["status"] = "AET"
    assert match_record(p2)["ph"] + match_record(p2)["pa"] == 1   # 加时赛补时里的点球是真判罚, 保留


def test_match_record_and_aggregate():
    a = match_record(parsed(1, 10, 20, 2, 1, [ev(10, "Card", "Yellow Card"), ev(20, "Card", "Yellow Card"), ev(20, "Card", "Yellow Card"),
                                              ev(20, "Card", "Red Card"), ev(10, "Goal", "Penalty"), ev(20, "Goal", "Missed Penalty"),
                                              ev(10, "Goal", "Normal Goal"), ev(99, "Card", "Yellow Card")]))
    assert (a["yh"], a["ya"], a["rh"], a["ra"], a["ph"], a["pa"]) == (1, 2, 0, 1, 1, 1)          # 非本场球队的事件被忽略, 普通进球不算点球
    b = match_record(parsed(2, 20, 10, 0, 0, [ev(20, "Card", "Yellow Card")], ts=1700100000))
    g = aggregate([a, b])
    assert g["n"] == 2 and g["yellow"] == 2.0 and g["red"] == 0.5 and g["pens"] == 1.0 and g["goals"] == 1.5
    assert abs(g["home_win"] - 0.5) < 1e-9 and abs(g["draw"] - 0.5) < 1e-9 and g["away_win"] == 0
    assert abs(g["yellow_home_share"] - 0.5) < 1e-9 and abs(g["pens_home_share"] - 0.5) < 1e-9
    assert aggregate([]) == {"n": 0}


def test_team_record_pov():
    a = match_record(parsed(1, 10, 20, 2, 1, [ev(10, "Card", "Yellow Card"), ev(20, "Card", "Yellow Card"), ev(20, "Goal", "Penalty")]))
    b = match_record(parsed(2, 20, 10, 0, 3, [ev(10, "Card", "Red Card"), ev(20, "Goal", "Missed Penalty")]))
    t = team_record([a, b], 10)
    assert t["n"] == 2 and (t["w"], t["d"], t["l"]) == (2, 0, 0) and t["y_for"] == 1 and t["y_against"] == 1
    assert t["p_for"] == 0 and t["p_against"] == 2 and t["r_for"] == 1 and t["r_against"] == 0
    assert team_record([a, b], 77)["n"] == 0


def test_zscore_and_verdict():
    # 例: 200 场点球均值 0.29 vs 基线 0.27 -> 不到半个标准误 -> 普通波动
    z = zscore(0.29, 0.269, 200)
    assert abs(z) < 0.7 and verdict(z) == "普通波动"
    assert verdict(zscore(0.60, 0.269, 60)) == "明显偏高" and verdict(zscore(0.05, 0.269, 150)) == "明显偏低"
    assert zscore(1, 0, 10) == 0.0 and zscore(1, 1, 0) == 0.0
    # 基线自身的噪音要计入: 同样的均值差, 基线样本越小越不显著(英超本赛季 110 场点球基线 0.200 很吵)
    noisy = zscore(0.348, 0.200, 66, 110)
    precise = zscore(0.348, 0.200, 66, 5091)
    assert noisy < precise and abs(noisy) < abs(precise)
    assert abs(zscore(0.348, 0.267, 66, 5091)) < 1.5                    # 对合并大样本基线只高 0.08, 属于普通波动


def test_competitions_scope():
    assert competitions(39) == [39, 40, 45, 48, 2, 3, 848]
    assert competitions(188) == [188, 17, 18]                 # 澳超: 只加亚冠
    assert competitions(253) == [253]                         # 美职联: 不加别的
    assert len(set(competitions(140))) == len(competitions(140))


def test_render_profile():
    recs = [match_record(parsed(i, 10, 20, 1, 1, [ev(10, "Card", "Yellow Card"), ev(20, "Card", "Yellow Card")], season=2026 if i < 3 else 2025)) for i in range(5)]
    data = {"records": recs, "variants": ["A. Madley×5"], "excluded": ["Bobby Madley×2"]}
    base = {"yellow": (3.86, 110, "该联赛本赛季"), "red": (0.178, 5091, "30 个联赛合并"), "pens": (0.267, 5091, "30 个联赛合并"), "goals": (2.95, 110, "该联赛本赛季")}
    t = render_profile(data, "Andrew Madley", "甲", "乙", 10, 20, base, 2026)
    assert "共 5 场" in t and "2026:3场" in t and "2025:2场" in t and "已排除同姓不同人 Bobby Madley×2" in t
    assert "基线 3.86[该联赛本赛季110场]" in t and "基线 0.267[30 个联赛合并5091场]" in t and "执法过主队甲: 5 场" in t and "口径统一" in t
    assert "已含基线自身的噪音" in t and "点球已排除点球大战" in t and "混有联赛、杯赛和欧战" in t
    empty = render_profile({"records": []}, "X", "甲", "乙", 1, 2, base, 2026)
    assert "没有找到他执法的已完赛场次" in empty


if __name__ == "__main__":
    for k, f in list(globals().items()):
        if k.startswith("test_"):
            f()
            print("ok", k)
