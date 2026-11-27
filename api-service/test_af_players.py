"""球员重要性的纯函数测试(不联网不连库)。python3 test_af_players.py"""
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
from api_football.injuries import _team_line  # noqa: E402
from api_football.lineups import regulars_missing  # noqa: E402
from api_football.players import classify, parse_players  # noqa: E402


def entry(pid, name, pos, apps, starts, minutes, goals=0):
    return {"player": {"id": pid, "name": name},
            "statistics": [{"games": {"position": pos, "appearences": apps, "lineups": starts, "minutes": minutes},
                            "goals": {"total": goals}}]}


def test_classify():
    assert classify(978, 11, 11) == "主力"
    assert classify(300, 5, 11) == "轮换"            # 分钟占比 30%, 首发率 45%
    assert classify(300, 7, 11) == "主力"            # 首发率 64% >= 60%
    assert classify(0, 0, 11) == "边缘"
    assert classify(100, 1, 0) == "未知"             # 没有球队场次


def test_parse_players_games_and_roles():
    out = parse_players([{"response": [entry(1, "A", "Attacker", 11, 11, 978, 5), entry(2, "B", "Defender", 3, 1, 90)]}])
    assert out["games"] == 11
    a, b = out["players"]["1"], out["players"]["2"]
    assert a["role"] == "主力" and a["goals"] == 5 and a["share"] == 0.99
    assert b["role"] == "边缘"


def item(name, role, pos="Defender", typ="Missing Fixture", share=0.6, starts=6, games=11, goals=0):
    d = {"name": name, "type": typ, "pos": pos, "reason": "Knee Injury"}
    if role:
        d.update({"role": role, "share": share, "starts": starts, "games": games, "goals": goals})
    return d


def test_team_line_with_roles_merges_edges():
    t = _team_line("客队", "乙", [item("Key", "主力", goals=5), item("Rot", "轮换", share=0.3, starts=3),
                              item("Nobody1", "边缘", share=0.0, starts=0), item("Nobody2", "边缘", share=0.0, starts=0)])
    assert "确认缺阵 4 人,其中主力 1、轮换 1、边缘/无出场 2" in t
    assert "Key(后卫·主力·首发 6/11、分钟占比 60%、进球 5" in t
    assert "另有基本不出场/边缘球员缺阵(影响很小): Nobody1、Nobody2" in t


def test_team_line_small_sample_flag_and_fallback():
    t = _team_line("主队", "甲", [item("K", "主力", games=3)])
    assert "样本小" in t
    t2 = _team_line("主队", "甲", [item("K", None)])                       # 没有出场数据 -> 降级写法
    assert "无法判断是否主力" in t2 and "主力 " not in t2.split("(")[0]


def test_regulars_missing():
    t = {"games": 11, "xi": [{"id": 1}], "regulars": [{"id": 1, "name": "InXI", "share": 0.9, "starts": 10, "goals": 0},
                                                      {"id": 2, "name": "Hurt", "share": 0.8, "starts": 9, "goals": 0},
                                                      {"id": 3, "name": "Rested", "share": 0.7, "starts": 8, "goals": 0}]}
    s = regulars_missing(t, {"Hurt": "在伤停名单(缺阵)"})
    assert "Hurt(分钟占比 80%、在伤停名单(缺阵))" in s and "Rested(分钟占比 70%、不在伤停名单" in s and "InXI" not in s
    assert "全部在首发" in regulars_missing({"games": 11, "xi": [{"id": 1}], "regulars": [{"id": 1, "name": "A", "share": 1, "starts": 11, "goals": 0}]}, {})
    assert regulars_missing({"xi": [], "regulars": []}, {}) == ""


if __name__ == "__main__":
    for k, f in list(globals().items()):
        if k.startswith("test_"):
            f()
            print("ok", k)
