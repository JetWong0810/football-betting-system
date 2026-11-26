"""同盘口历史净胜分布测试(用内存构造的表, 不连库)。python3 test_margin_dist.py"""
import os
import sys
from collections import Counter

sys.path.insert(0, os.path.dirname(__file__))
from match_chat import margin_dist as md  # noqa: E402


def table():
    # 主让1球(H,1.0): 热门净胜球分布 0:20 1:30 2+:... 共 500
    t = {("H", 1.0): Counter({-2: 20, -1: 40, 0: 100, 1: 140, 2: 120, 3: 80}),
         ("H", 1.25): Counter({-1: 10, 0: 20, 1: 30}),             # 样本不足, 需合并
         ("H", 1.5): Counter({0: 100, 1: 100, 2: 100}),
         ("0", 0.0): Counter({-1: 200, 0: 300, 1: 250})}
    return t


def test_lookup_and_merge():
    t = table()
    a = md.lookup(1.0, t)
    assert a["n"] == 500 and a["merged"] is None and a["fav"] == "H"
    b = md.lookup(1.25, t)                                         # 1.25 只有 60 场, 合并相邻档(1.0 / 1.5)
    assert b["n"] >= md.MIN_N and b["merged"] is not None, b
    assert md.lookup(2.75, t) is None                              # 没有任何样本


def test_cover_probs():
    d = Counter({-1: 25, 0: 25, 1: 25, 2: 25})                      # 热门净胜球
    cp = md.cover_probs(d, 1.0)                                      # 让1球: 净胜2 全赢, 1 走水, 0/-1 全输
    assert abs(cp["全赢"] - .25) < 1e-9 and abs(cp["走水"] - .25) < 1e-9 and abs(cp["全输"] - .5) < 1e-9
    assert abs(cp["eff"] - 1 / 3) < 1e-9
    cq = md.cover_probs(d, 1.25)                                     # 让1.25: 净胜1 输半, 净胜2 全赢
    assert abs(cq["输半"] - .25) < 1e-9 and abs(cq["全赢"] - .25) < 1e-9
    # 让0.75: 净胜2+ 全赢, 净胜1 赢半, 其余全输 -> eff = (0.5+0.25*0.5)... 用均匀分布核对
    dq = Counter({-1: 25, 0: 25, 1: 25, 2: 25})
    cr = md.cover_probs(dq, 0.75)
    assert abs(cr["赢半"] - .25) < 1e-9 and abs(cr["全赢"] - .25) < 1e-9 and abs(cr["全输"] - .5) < 1e-9
    assert abs(cr["eff"] - (0.25 + 0.125) / (0.25 + 0.125 + 0.5)) < 1e-9, cr
    assert abs(sum(cq[k] for k in ("全赢", "赢半", "走水", "输半", "全输")) - 1) < 1e-9


def test_text():
    t = md.margin_text(1.0, "甲", "乙", table())
    assert "甲让1" in t and "净胜≥2球 40.0%" in t and "平 20.0%" in t and "全赢 40.0%" in t and "走水 28.0%" in t, t
    t0 = md.margin_text(0, "甲", "乙", table())
    assert "平手" in t0 and "没有上下盘之分" in t0
    assert md.margin_text(3.0, "甲", "乙", table()) == ""


if __name__ == "__main__":
    for n, f in list(globals().items()):
        if n.startswith("test_"):
            f()
            print("ok", n)
