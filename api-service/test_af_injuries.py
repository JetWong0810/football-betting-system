"""伤停块的纯函数测试(不联网不连库)。python3 test_af_injuries.py"""
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
from api_football.injuries import MAX_PER_TEAM, _team_line  # noqa: E402
from match_chat.service import wanted_sections  # noqa: E402


def r(name, pos, typ="Missing Fixture", reason="Knee Injury"):
    return {"name": name, "pos": pos, "type": typ, "reason": reason}


def test_position_summary():
    t = _team_line("主队", "甲", [r("A", "Defender"), r("B", "Defender"), r("C", "Goalkeeper"), r("D", None)])
    assert "确认缺阵 4 人" in t and "后卫2" in t and "门将1" in t and "位置未知1" in t


def test_questionable_separate():
    t = _team_line("客队", "乙", [r("A", "Attacker"), r("B", "Midfielder", typ="Questionable")])
    assert "确认缺阵 1 人" in t and "存疑: B" in t


def test_cap():
    rows = [r(f"P{i}", "Defender") for i in range(MAX_PER_TEAM + 4)]
    t = _team_line("主队", "甲", rows)
    assert f"P{MAX_PER_TEAM - 1}" in t and f"P{MAX_PER_TEAM}" not in t and f"共{MAX_PER_TEAM + 4}人" in t


def test_trigger_requires_intent():
    assert "inj" in wanted_sections("请关联本场伤停数据,分析影响")
    assert "inj" not in wanted_sections("伤停一般怎么看")             # 没有"关联/本场"意图, 不误触发
    assert "inj" in wanted_sections("请关联本场全部数据")


if __name__ == "__main__":
    for k, v in list(globals().items()):
        if k.startswith("test_"):
            v()
            print("ok", k)
