"""首发块的纯函数测试(不联网不连库)。python3 test_af_lineups.py"""
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
from api_football.lineups import _xi_text, parse_lineups, rotation  # noqa: E402
from match_chat.service import wanted_sections  # noqa: E402


def team(tid, n=11, formation="4-3-3"):
    pos = ["G"] + ["D"] * 4 + ["M"] * 3 + ["F"] * 3
    return {"team": {"id": tid, "name": f"T{tid}"}, "formation": formation, "coach": {"name": "C"},
            "startXI": [{"player": {"id": tid * 100 + i, "name": f"P{tid}{i}", "pos": pos[i % 11], "grid": "1:1"}} for i in range(n)]}


def test_parse_requires_two_full_teams():
    assert parse_lineups([]) is None
    assert parse_lineups([team(1)]) is None
    assert parse_lineups([team(1), team(2, n=5)]) is None            # 数据不全当作未公布
    lu = parse_lineups([team(1), team(2)])
    assert set(lu) == {"1", "2"} and len(lu["1"]["xi"]) == 11


def test_rotation():
    assert rotation([1, 2, 3, 4], [1, 2, 3, 4]) == 0
    assert rotation([1, 2, 3, 9], [1, 2, 3, 4]) == 1


def test_xi_text_groups_and_rotation():
    t = parse_lineups([team(1), team(2)])["1"]
    t["rotation"], t["prev"] = 4, {"date": "2026-11-08", "opp": "X", "comp": "Cup"}
    s = _xi_text(t)
    assert "阵型 4-3-3" in s and "门将" in s and "后卫" in s and "换了 4 人" in s and "Cup" in s


def test_trigger():
    assert "lineup" in wanted_sections("请关联本场首发数据")
    assert "lineup" not in wanted_sections("首发一般几点公布")           # 没有关联意图不触发
    assert "lineup" in wanted_sections("请关联本场全部数据")


if __name__ == "__main__":
    for k, f in list(globals().items()):
        if k.startswith("test_"):
            f()
            print("ok", k)
