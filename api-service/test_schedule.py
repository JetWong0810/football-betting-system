"""赛程密度的纯函数测试(不联网不连库)。python3 test_schedule.py"""
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
from match_chat.schedule import is_cup, schedule_text, team_schedule  # noqa: E402
from datetime import date  # noqa: E402


def r(d, comp="英超"):
    return {"date": d, "competition": comp}


def test_rest_and_n14_and_next():
    s = team_schedule(date(2026, 11, 28), [r("2026-11-21"), r("2026-11-24", "欧冠"), r("2026-10-01")],
                      [r("2026-11-28"), r("2026-12-02", "欧联杯")])
    assert s["rest"] == 4 and s["last_comp"] == "欧冠" and s["n14"] == 2          # 10-01 在 14 天窗口外
    assert s["next_gap"] == 4 and s["next_comp"] == "欧联杯"                       # 同日的本场自己不算下一场


def test_excludes_matches_on_or_after_kickoff_from_past():
    s = team_schedule(date(2026, 11, 28), [r("2026-11-28"), r("2026-11-30")], [])
    assert s["rest"] is None and s["n14"] is None


def test_cup_detection():
    assert is_cup("欧冠") and is_cup("英联杯") and is_cup("足总杯") and not is_cup("英超")


def test_text_flags_and_differential():
    t = schedule_text("2026-11-28", "甲", "乙",
                      [r("2026-11-25", "欧冠")], [r("2026-11-21")],
                      [r("2026-12-01", "欧冠")], [r("2026-12-05")])
    assert "休息天数差: 乙多休息 4 天" in t and "杯赛/欧战,可能影响本场轮换" in t and "t=-1.8" in t


def test_no_data_returns_empty():
    assert schedule_text("2026-11-28", "甲", "乙", [], [], [], []) == ""
    assert schedule_text("坏日期", "甲", "乙", [r("2026-11-21")], [], [], []) == ""


if __name__ == "__main__":
    for k, f in list(globals().items()):
        if k.startswith("test_"):
            f()
            print("ok", k)
