"""本赛季比赛库的纯函数测试(不联网不连库)。python3 test_af_hist.py"""
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
from api_football.geo import pick_result  # noqa: E402
from api_football.hist import haversine_km, parse_detail  # noqa: E402
from api_football.team_style import bucket_of, compare_lineup, rotation_changes, summarize  # noqa: E402


def detail(fid=1, with_stats=True):
    return {
        "fixture": {"id": fid, "timestamp": 1700000000, "referee": "R", "status": {"short": "FT"}, "venue": {"id": 9, "name": "S", "city": "London"}},
        "league": {"id": 39, "season": 2026, "round": "Regular Season - 3"},
        "teams": {"home": {"id": 10}, "away": {"id": 20}}, "goals": {"home": 2, "away": 1}, "score": {"halftime": {"home": 1, "away": 0}},
        "events": [{"time": {"elapsed": 12, "extra": None}, "team": {"id": 10}, "player": {"id": 7, "name": "A"}, "assist": {"name": "B"}, "type": "Goal", "detail": "Normal Goal"},
                   {"time": {"elapsed": 45, "extra": 2}, "team": {"id": 20}, "player": {"id": 8, "name": "C"}, "assist": {"name": None}, "type": "subst", "detail": "Substitution 1"}],
        "lineups": [{"team": {"id": 10}, "formation": "4-3-3", "coach": {"id": 5, "name": "Coach"},
                     "startXI": [{"player": {"id": i, "name": f"P{i}", "pos": "M", "grid": "1:1"}} for i in range(11)], "substitutes": [{"player": {"id": 99, "name": "S", "pos": "F"}}]}],
        "statistics": ([{"team": {"id": 10}, "statistics": [{"type": "Total Shots", "value": 12}, {"type": "expected_goals", "value": "1.40"}, {"type": "Junk", "value": 1}]}] if with_stats else []),
    }


def test_parse_detail():
    p = parse_detail(detail())
    m = p["match"]
    assert m["fixture_id"] == 1 and m["league_id"] == 39 and m["season"] == 2026 and m["status"] == "FT" and m["hg"] == 2 and m["hth"] == 1 and m["has_stats"] == 1
    assert p["venue"] == {"id": 9, "name": "S", "city": "London"}
    assert p["lineups"][0]["formation"] == "4-3-3" and p["lineups"][0]["coach_id"] == 5 and len(p["lineups"][0]["xi"]) == 11 and len(p["lineups"][0]["subs"]) == 1
    assert p["events"][0]["minute"] == 12 and p["events"][0]["extra"] == 0 and p["events"][1]["extra"] == 2
    assert p["stats"] == [{"team_id": 10, "stats": {"Total Shots": 12, "expected_goals": "1.40"}}]          # 只保留关心的统计键
    assert parse_detail(detail(with_stats=False))["match"]["has_stats"] == 0


def test_rotation_and_buckets():
    assert rotation_changes([[1, 2, 3], [1, 2, 4], [5, 6, 4]]) == [1, 2]
    assert rotation_changes([[1, 2]]) == []
    assert bucket_of(10) == "0-15" and bucket_of(45) == "31-45+" and bucket_of(47) == "31-45+" and bucket_of(48) == "46-60" and bucket_of(95) == "76-90+"


def mk(fid, form, xi, home=True, coach=5):
    return {"fid": fid, "ts": fid, "is_home": home, "formation": form, "xi": xi, "coach_id": coach, "coach_name": f"C{coach}"}


def test_summarize_and_coach_change():
    ms = [mk(1, "3-4-2-1", [1, 2, 3], coach=4), mk(2, "3-4-2-1", [1, 2, 4], coach=5), mk(3, "4-2-3-1", [1, 5, 6], home=False, coach=5)]
    s = summarize(ms, [60, 62], [10, 50, 80])
    assert s["top_formations"][0] == ("3-4-2-1", 2) and s["changes"] == [1, 2] and s["change_mean"] == 1.5 and s["change_max"] == 2
    assert s["coach"] == (5, "C5") and s["games_under_coach"] == 2 and s["coach_changed"] is True
    assert s["away_top"] == [("4-2-3-1", 1)] and s["first_sub_mean"] == 61.0
    assert s["goal_buckets"] == {"0-15": 1, "46-60": 1, "76-90+": 1}
    assert summarize([], [], [])["n"] == 0


def test_compare_uses_team_baseline():
    # 球队自己的基线: 平均换 1.4 人、最多 2 人 -> 换 4 人异常; 基线 2.8/最多 5 -> 换 4 人正常
    calm = [mk(i, "3-4-2-1", list(range(i, i + 11))) for i in range(1, 8)]               # 每场只换 1 人
    r = compare_lineup([100, 101, 102, 103] + list(range(5, 12)), "3-4-2-1", calm, True)
    assert r["vs_last_changes"] >= 4 and r["abnormal"] is True and r["formation_changed"] is False
    busy = []
    base = list(range(11))
    for i in range(7):
        base = base[3:] + [100 + i * 3 + k for k in range(3)] if i % 2 else base[2:] + [200 + i * 2, 201 + i * 2]
        busy.append(mk(i + 1, "4-2-3-1", list(base)))
    r2 = compare_lineup(busy[-1]["xi"][:-4] + [900, 901, 902, 903], "4-2-3-1", busy, True)
    assert r2["vs_last_changes"] == 4 and r2["abnormal"] is False


def test_dates_to_sync():
    from datetime import datetime
    from api_football.hist_auto import dates_to_sync
    assert dates_to_sync(datetime(2026, 11, 28, 1, 0)) == ['2026-11-28', '2026-11-27']
    assert dates_to_sync(datetime(2026, 1, 1), 3) == ['2026-01-01', '2025-12-31', '2025-12-30']


def test_style_text_coach_by_id_and_travel():
    from api_football.style_text import lineup_compare_text, travel_text
    hist = [mk(i, "4-2-3-1", list(range(i, i + 11)), coach=5) for i in range(1, 8)]
    for h in hist:
        h["names"] = {x: f"P{x}" for x in h["xi"]}
        h["coach_name"] = "Nazri Nasir"                                  # 历史里是全名
    xi = [{"id": i, "name": f"P{i}"} for i in range(8, 19)]
    same = lineup_compare_text("主队", "甲", xi, "4-2-3-1", "N. Nasir", hist, True, coach_id=5)       # 名字写法不同但 id 相同
    assert "教练变更" not in same and "换了" in same and "基线" in same or "平均换" in same
    changed = lineup_compare_text("主队", "甲", xi, "4-2-3-1", "New Guy", hist, True, coach_id=99)
    assert "教练变更" in changed
    unknown = lineup_compare_text("主队", "甲", xi, "4-2-3-1", "N. Nasir", hist, True, coach_id=None)  # 本场没有 id: 不下结论
    assert "教练变更" not in unknown
    assert lineup_compare_text("主队", "甲", xi, "4-2-3-1", None, [], True) == ""
    few = lineup_compare_text("主队", "甲", xi, "4-2-3-1", None, hist[:3], True, coach_id=5)
    assert "样本仅 3 场" in few
    assert travel_text("乙", {"km": 400, "tz_diff": 0.0, "from": "A", "to": "B"}) == ""                  # 不远不提示
    t = travel_text("乙", {"km": 3809, "tz_diff": 0.0, "from": "Shanghai", "to": "Singapore"})
    assert "3809 公里" in t and "时差" not in t and "没有回测" in t                                         # 时差为 0 不写
    assert "时差 +3 小时" in travel_text("乙", {"km": 900, "tz_diff": 3.0, "from": "A", "to": "B"})


def test_goal_timing_curve():
    from api_football.goal_timing import BINS, bin_index, curve_from_counts, remaining_mu, share_after
    assert bin_index(1) == 0 and bin_index(15) == 0 and bin_index(16) == 1 and bin_index(45) == 2 and bin_index(46) == 3 and bin_index(90) == 5 and bin_index(105) is None
    assert bin_index(0) == 0                                                      # 0 分钟当作第 1 分钟
    flat = curve_from_counts([10] * 6)
    assert abs(sum(flat) - 1) < 1e-9
    assert share_after(0, flat) == 1.0 and share_after(90, flat) == 0.0
    assert abs(share_after(45, flat) - 0.5) < 1e-9 and abs(share_after(60, flat) - 1 / 3) < 1e-9
    assert abs(share_after(7.5, flat) - (1 - 1 / 12)) < 1e-9                       # 桶内线性插值
    late = curve_from_counts([5, 10, 15, 15, 25, 30])                              # 后段进球更多
    assert share_after(60, late) > share_after(60, flat)                           # 过了 60 分钟后, 剩余进球占比高于均匀假设
    prev = 2.0
    for m in range(0, 91, 5):                                                      # 单调不增
        v = share_after(m, late)
        assert v <= prev + 1e-12
        prev = v
    assert abs(remaining_mu(2.8, 60, flat) - 2.8 / 3) < 1e-9
    assert len(BINS) == 6


def test_geo_query_candidates():
    from api_football.geo import query_candidates
    assert query_candidates('Bournemouth, Dorset') == ['Bournemouth', 'Bournemouth, Dorset']
    assert query_candidates('London') == ['London'] and query_candidates('') == []


def test_geo_helpers():
    assert abs(haversine_km(51.5, -0.12, 48.85, 2.35) - 344) < 6          # 伦敦-巴黎约 344km
    res = [{"country": "United States", "country_code": "US", "admin1": "Ohio"}, {"country": "United Kingdom", "country_code": "GB", "admin1": "England"}]
    assert pick_result(res, "England")["country_code"] == "GB"            # AF 国家名 England 对应英国
    assert pick_result(res, "USA")["country_code"] == "US"                # USA 对应 United States
    assert pick_result([], "x") is None


def test_geo_country_mismatch_returns_none_and_region_hint():
    from api_football.geo import norm_country, region_of
    uk_first = [{"country": "United Kingdom", "admin1": "England"}, {"country": "United States", "admin1": "Pennsylvania"},
                {"country": "United States", "admin1": "Ohio"}]
    assert pick_result(uk_first, "USA", "Pennsylvania")["admin1"] == "Pennsylvania"       # 州提示优先
    assert pick_result(uk_first, "USA")["country"] == "United States"                      # 没州提示也不会取到英国
    assert pick_result([{"country": "Mozambique"}], "Portugal") is None                    # 国家对不上宁可不猜(Lisboa 曾被编到马普托)
    assert norm_country("Saudi-Arabia") == "saudi arabia" and norm_country("Scotland") == "united kingdom"
    assert region_of("Chester, Pennsylvania") == "Pennsylvania" and region_of("London") is None


if __name__ == "__main__":
    for k, f in list(globals().items()):
        if k.startswith("test_"):
            f()
            print("ok", k)
