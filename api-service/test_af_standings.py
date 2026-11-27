"""战意判定的纯函数测试(不联网不连库)。python3 test_af_standings.py"""
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
from api_football.standings import classify, parse_table  # noqa: E402


def table(points, played, rel_from=None):
    rows = []
    for i, (p, g) in enumerate(zip(points, played)):
        rows.append({"team_id": 100 + i, "rank": i + 1, "points": p, "played": g,
                     "description": "Relegation - Championship" if rel_from is not None and i >= rel_from else None})
    return rows


def test_not_applicable_cases():
    assert classify(table([10] * 10, [30] * 10), 18) is None                 # 队数不足 16
    assert classify(table(list(range(70, 50, -1)), [30] * 20), 30) is None   # 20 队但总轮数不是 38(非双循环)


def test_stakes_labels_late_season():
    pts = [80, 75, 72, 70, 66, 60, 55, 52, 50, 48, 47, 46, 45, 44, 42, 40, 38, 36, 30, 25]   # 20 队, 已踢 33 轮, 剩 5
    cl = classify(table(pts, [33] * 20, rel_from=17), 38)
    assert cl["100"]["stake"] == "up"                       # 榜首
    assert cl["104"]["stake"] == "up"                       # 第5名, 距第4名 4 分 <= 2*5
    assert cl["108"]["stake"] == "none"                     # 第9名: 距前四 20 分够不着; 距保级线(第17名 38 分) +12 > 10 -> 无欲无求
    assert cl["116"]["stake"] == "down"                     # 第17名, 在保级线上
    assert cl["119"]["stake"] == "down"                     # 垫底


def test_relegation_line_from_description_and_fallback():
    pts = [80, 75, 72, 70, 66, 60, 55, 52, 50, 48, 47, 46, 45, 44, 42, 40, 38, 36, 30, 25]
    a = classify(table(pts, [33] * 20, rel_from=17), 38)       # 标签: 第 18 名起降级 -> 保级线上第一名=第 17 名(38 分)
    b = classify(table(pts, [33] * 20, rel_from=None), 38)     # 没有标签: 退回倒数第 4 名(同为第 17 名)
    c = classify(table(pts, [33] * 20, rel_from=16), 38)       # 标签: 第 17 名起降级 -> 保级线上第一名=第 16 名(40 分)
    assert a["116"]["gap_safe"] == 0 and b["116"]["gap_safe"] == 0 and c["116"]["gap_safe"] == -2


def test_parse_table_rejects_grouped_leagues():
    one = [{"league": {"standings": [[{"team": {"id": 1}, "rank": 1, "points": 3, "all": {"played": 1}, "description": None}]]}}]
    assert parse_table(one)[0]["team_id"] == 1
    two = [{"league": {"standings": [[], []]}}]
    assert parse_table(two) is None and parse_table([]) is None


if __name__ == "__main__":
    for k, f in list(globals().items()):
        if k.startswith("test_"):
            f()
            print("ok", k)
