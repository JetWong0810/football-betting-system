"""大小球概率分布的纯函数测试(不联网不连库)。python3 test_ou_model.py"""
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
from match_chat.ou_model import (break_even_water, ev, fit_mu, lines_around, ou_block, outcomes, pick_source,  # noqa: E402
                                 pmf)


def test_pmf_sums_to_one():
    assert abs(sum(pmf(2.7)) - 1) < 1e-6


def test_outcomes_quarter_and_whole_lines():
    o = outcomes(3.3, 3.25)                      # 买大3.25: >=4 全赢, =3 输半, <=2 全输
    p = pmf(3.3)
    assert abs(o["全赢"] - sum(p[4:])) < 1e-9 and abs(o["输半"] - p[3]) < 1e-9 and abs(o["全输"] - sum(p[:3])) < 1e-9
    o = outcomes(3.3, 3.0)                       # 买大3.0: =3 走水
    assert abs(o["走水"] - p[3]) < 1e-9
    o = outcomes(2.7, 2.75, "over")              # 买大2.75: =3 赢半, <=2 全输
    assert abs(o["赢半"] - pmf(2.7)[3]) < 1e-9


def test_fit_mu_roundtrip():
    n = 0
    for mu, line in ((2.2, 2.0), (2.2, 2.25), (2.7, 2.5), (2.7, 2.75), (3.4, 3.25), (3.4, 3.5), (3.0, 2.75)):
        eff = outcomes(mu, line)["eff"]
        wo = 0.92
        io = 1 / (1 + wo)
        wu = 1 / (io * (1 - eff) / eff) - 1       # 让去水后买大概率恰为 eff
        got = fit_mu(line, wo, wu)
        assert got is not None and abs(got - mu) < 0.01, (mu, line, got)
        n += 1
    assert n == 7


def test_break_even_and_ev_consistent():
    mu, line = 3.4, 3.25
    w = break_even_water(mu, line, "over")
    assert abs(ev(mu, line, w, "over")) < 1e-6
    assert ev(mu, line, w + 0.1, "over") > 0 > ev(mu, line, w - 0.1, "over")
    assert break_even_water(mu, 3.0, "over") < break_even_water(mu, 3.5, "over")      # 线越高, 买大越难, 需要的水位越高


def test_invalid_waters_rejected():
    assert fit_mu(2.5, 0.2, 1.0) is None and fit_mu(2.5, 1.0, 2.0) is None


def test_pick_source_prefers_pinnacle():
    ou = [{"bookmaker": "Bet365", "current": {"line": 2.75, "over": 0.9, "under": 0.95}},
          {"bookmaker": "Pinnacle", "current": {"line": 2.5, "over": 0.88, "under": 1.0}}]
    assert pick_source(ou)[0] == "Pinnacle"
    assert pick_source([{"bookmaker": "X", "current": {"line": 2.5, "over": 0.1, "under": 1.0}}]) is None   # 水位失真被排除


def test_lines_and_block():
    assert 3.25 in lines_around(3.25) and min(lines_around(1.5)) >= 1.0
    t = ou_block([{"bookmaker": "Pinnacle", "current": {"line": 3.25, "over": 0.95, "under": 0.95}}])
    assert "【大小球概率分布】" in t and "μ=" in t and "3.25 线" in t and "0.046" in t
    t2 = ou_block([{"bookmaker": "Pinnacle", "current": {"line": 2.5, "over": 0.95, "under": 0.95}}], 0.12, "战意")
    assert "已验证因素修正" in t2
    assert ou_block([]) == ""


def test_recent_goals_text_needs_five_games():
    from match_chat.ou_model import recent_goals_text
    assert recent_goals_text("甲", [3, 1, 2], "乙", [2, 2, 2, 2, 2]) == ""
    t = recent_goals_text("甲", [3, 1, 2, 4, 0], "乙", [2, 2, 3, 1, 5])
    assert "场均总进球 2.0" in t and "≥3 球 2/5" in t and "≤1 球 2/5" in t and "相关系数≈0" in t


def test_ou_request_bundles_inputs():
    from match_chat.service import wanted_sections
    w = wanted_sections("请关联本场大小球相关数据,判断总进球偏大还是偏小")
    assert {"odds", "inj", "lineup", "recent"} <= set(w)
    assert wanted_sections("大小球一般怎么看") == []                    # 没有关联意图不触发
    assert "inj" not in wanted_sections("请关联本场盘口数据")            # 不问大小球时不自动带伤停


if __name__ == "__main__":
    for k, f in list(globals().items()):
        if k.startswith("test_"):
            f()
            print("ok", k)
