"""价格与先验层、倾向结算的测试(纯函数, 不联网不连库)。python3 test_edge.py"""
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
from match_chat import edge  # noqa: E402


def comp(name, h, wh, wa):
    return {"bookmaker": name, "current": {"handicap": h, "home": wh, "away": wa}}


def test_classify_and_signal():
    assert edge.classify_move(1.0, 1.5) == ("deeper", 0.5)          # 主让加深
    assert edge.classify_move(-1.0, -0.75)[0] == "shallower"        # 主受让变浅 = 上盘(客)变浅
    assert edge.classify_move(0.5, -0.5) is None and edge.classify_move(0, 0.25) is None
    t = edge.signal_text(1.0, 1.5, "甲", "乙")
    assert "上盘(甲)" in t and "加深 0.5 球" in t and "46.3%" in t and "n=1470" in t, t
    t = edge.signal_text(-1.0, -1.25, "甲", "乙")
    assert "上盘(乙)" in t and "48.1%" in t
    assert "无可比" in edge.signal_text(0, 0, "甲", "乙")


def test_best_price_and_ev():
    asian = [comp("Bet365", 1.0, 0.98, 0.88), comp("Pinnacle", 1.0, 0.95, 0.95), comp("皇冠", 1.0, 1.02, 0.80),
             comp("澳门", 1.25, 0.90, 0.95)]
    bp = edge.best_price(asian)
    assert bp["n_same"] == 3 and bp["n_all"] == 4
    assert bp["home"] == (1.02, "皇冠") and bp["away"] == (0.95, "Pinnacle")      # 不同盘口的澳门不参与
    assert bp["pin"] == (50.0, 50.0)
    assert abs(bp["ev_home"] - 1.0) < 0.05 and abs(bp["ev_away"] - (-2.5)) < 0.05, bp
    t = edge.best_price_text(asian, "甲", "乙")
    assert "皇冠" in t and "买甲最优价 +1.0%" in t, t
    assert "不足 2%" in t, t                                  # +1.0% 在误差内
    asian2 = [comp("Bet365", 1.0, 0.98, 0.88), comp("Pinnacle", 1.0, 0.90, 0.90), comp("皇冠", 1.0, 1.05, 0.80)]
    assert "价格上相对 Pinnacle 有优势" in edge.best_price_text(asian2, "甲", "乙")
    asian3 = [comp("Pinnacle", 1.0, 0.95, 0.95), comp("Bet365", 1.0, 0.90, 0.90)]
    assert "两边期望都不为正" in edge.best_price_text(asian3, "甲", "乙")
    assert "无法估算" in edge.best_price_text([comp("Bet365", 1.0, 0.98, 0.88)], "甲", "乙")
    assert edge.best_price([]) is None


def item(name, h0, h1, w0h, w0a, w1h, w1a):
    return {"bookmaker": name, "initial": {"handicap": h0, "home": w0h, "away": w0a},
            "current": {"handicap": h1, "home": w1h, "away": w1a}}


def test_water_signal():
    # 主让1(上盘=甲), 盘口不变, 主水 0.95->0.85(降0.10) => drop
    a = [item("Bet365", 1.0, 1.0, 0.95, 0.90, 0.85, 1.00), item("皇冠", 1.0, 1.0, 0.92, 0.93, 0.86, 0.97),
         item("Pinnacle", 1.0, 1.0, 0.90, 0.95, 0.96, 0.93)]
    w = edge.water_signal(a, "甲", "乙")
    assert w["kind"] == "drop" and w["up"] == "甲" and abs(w["delta"] + 0.10) < 1e-9
    assert w["tally"] == {"drop": 2, "rise": 1, "flat": 0}, w["tally"]
    t = edge.water_signal_text(a, "甲", "乙")
    assert "53.1%" in t and "n=3884" in t and "顺势" in t and "上盘(甲)水位 0.95→0.85" in t, t
    # 主受让(上盘=客): 客水升 => rise
    b = [item("Bet365", -0.5, -0.5, 0.90, 0.80, 0.88, 0.90)]
    w = edge.water_signal(b, "甲", "乙")
    assert w["kind"] == "rise" and w["up"] == "乙", w
    # 盘口变了 / 平手盘 / 无 Bet365: 不适用
    assert edge.water_signal([item("Bet365", 1.0, 1.25, 0.9, 0.9, 0.9, 0.9)], "甲", "乙") is None
    assert edge.water_signal([item("Bet365", 0, 0, 0.9, 0.9, 0.8, 1.0)], "甲", "乙") is None
    assert edge.water_signal([item("皇冠", 1.0, 1.0, 0.9, 0.9, 0.8, 1.0)], "甲", "乙") is None
    assert "不适用" in edge.water_signal_text([], "甲", "乙")


def test_prior():
    eu = [{"bookmaker": "Pinnacle", "current": {"win": 2.0, "draw": 4.0, "lose": 4.0}}]
    t = edge.prior_text(eu, "甲", "乙")
    assert "Pinnacle" in t and "甲胜 50.0%" in t and "平 25.0%" in t, t
    assert edge.prior_text([], "甲", "乙") == ""


def test_settle_ah():
    r = edge.settle_ah("上盘", 0.75, 0.90, 0.95, 1, 0)           # 主让0.75, 主赢1球 -> 主赢半
    assert r["word"] == "赢半" and abs(r["units"] - 0.45) < 1e-9 and r["pickHome"]
    r = edge.settle_ah("下盘", 0.75, 0.90, 0.95, 1, 0)           # 下盘=客, 输半
    assert r["word"] == "输半" and r["units"] == -0.5
    r = edge.settle_ah("上盘", -1.0, 0.9, 0.9, 0, 1)             # 主受让1, 上盘=客, 客赢1球 -> 走水
    assert r["word"] == "走水" and r["units"] == 0
    assert edge.settle_ah("上盘", 0, 0.9, 0.9, 1, 0) is None and edge.settle_ah("不确定", 0.5, 0.9, 0.9, 1, 0) is None


def test_settle_ou_and_tally():
    r = edge.settle_ou("大球", 2.25, 0.95, 0.85, 2, 1)           # 3球 -> 大全赢
    assert r["word"] == "全赢" and r["units"] == 0.95
    r2 = edge.settle_ou("小球", 2.25, 0.95, 0.85, 1, 1)          # 2球 -> 小赢半
    assert r2["word"] == "赢半" and abs(r2["units"] - 0.425) < 1e-9
    t = edge.tally([r, r2, {"word": "全输", "units": -1.0}])
    assert t["n"] == 3 and t["hit"] == 60.0 and t["roi"] == 12.5, t


if __name__ == "__main__":
    for n, f in list(globals().items()):
        if n.startswith("test_"):
            f()
            print("ok", n)
