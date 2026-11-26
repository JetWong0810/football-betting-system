"""滚球记录的解析函数测试(纯函数, 用真实返回的结构)。python3 test_af_live.py"""
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
from api_football.live import main_pair, parse_odds  # noqa: E402


def v(side, odd, line, main=None, susp=False):
    return {"value": side, "odd": str(odd), "handicap": str(line), "main": main, "suspended": susp}


def test_ah_single_line_negated_away():
    # 实测形态: 主队一侧 +4.5, 客队一侧 -4.5
    assert main_pair([v("Home", 1.975, 4.5), v("Away", 1.825, -4.5)], away_negated=True) == (4.5, 1.975, 1.825)


def test_ah_prefers_main_flag():
    vals = [v("Home", 1.675, -0.75, False), v("Away", 2.05, 0.75, False),
            v("Home", 2.025, -1, True), v("Away", 1.775, 1, True),
            v("Home", 1.525, -0.5, False), v("Away", 2.35, 0.5, False)]
    assert main_pair(vals, away_negated=True) == (-1.0, 2.025, 1.775)


def test_no_main_flag_picks_most_balanced():
    vals = [v("Home", 1.4, -1.5), v("Away", 2.9, 1.5), v("Home", 1.95, -1.0), v("Away", 1.85, 1.0)]
    assert main_pair(vals, away_negated=True)[0] == -1.0


def test_ou_same_line_and_suspended_skipped():
    assert main_pair([v("Over", 1.8, 2.5), v("Under", 2.0, 2.5)], "Over", "Under") == (2.5, 1.8, 2.0)
    assert main_pair([v("Over", 1.8, 2.5, susp=True), v("Under", 2.0, 2.5)], "Over", "Under") is None


def test_parse_odds_entry():
    e = {"update": "2026-11-26T11:33:30+00:00", "status": {"stopped": False},
         "odds": [{"name": "Asian Handicap", "values": [v("Home", 2.0, -0.25), v("Away", 1.8, 0.25)]},
                  {"name": "Match Corners", "values": []}]}
    o = parse_odds(e)
    assert o["ah"] == (-0.25, 2.0, 1.8) and o["ou"] is None and list(o["raw"]) == ["Asian Handicap"]


if __name__ == "__main__":
    for k, f in list(globals().items()):
        if k.startswith("test_"):
            f()
            print("ok", k)
