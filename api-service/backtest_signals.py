"""复算聊天上下文里引用的回测数字(只读库): python3 backtest_signals.py
Bet365 开盘→终盘的上盘加深/变浅/不变分组上盘赢盘率, 以及水位格式一致样本上的买上盘/买下盘 ROI。
edge.py 里的 SIGNALS / SIGNAL_NOTE 数字来自这里, 数据变多后重跑并更新。"""
import collections
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
from database import get_db  # noqa: E402
from jczq_similar_odds import _ah_outcome  # noqa: E402


def _rate(rs):
    t = collections.Counter()
    for r in rs:
        o = _ah_outcome(int(r["hs"]), int(r["a"]), float(r["ch"]))
        if o:
            t[o[1]] += 1
    up, lo = t["upper"] + .5 * t["half_up"], t["lower"] + .5 * t["half_down"]
    return (round(up / (up + lo) * 100, 1), int(up + lo)) if up + lo else None


def _pnl(label, side, w):
    if label == "走水":
        return 0
    if label == ("上盘" if side == "upper" else "下盘"):
        return w
    if label == ("半上" if side == "upper" else "半下"):
        return w / 2
    return -1 if label in ("上盘", "下盘") else -0.5


COMPANY = "Bet365-500"      # 500.com 来源(32095 场)。足彩网来源(company='Bet365')约 12% 终盘混入开赛后滚球盘口, 不要用


def main():
    with get_db() as c:
        cur = c.cursor()
        cur.execute("""SELECT m.match_timestamp ts, m.home_score hs, m.away_score a, h.open_handicap oh, h.close_handicap ch,
                       h.close_home_odds ho, h.close_away_odds ao
                       FROM matches m JOIN jczq_ah_history h ON h.match_id=m.match_id
                       WHERE m.home_score IS NOT NULL AND h.open_handicap IS NOT NULL AND h.close_handicap IS NOT NULL
                       AND h.company = %s""", (COMPANY,))
        rows = sorted(cur.fetchall(), key=lambda r: r["ts"] or 0)
    ok = [r for r in rows if float(r["ch"]) != 0 and float(r["oh"]) != 0 and (float(r["oh"]) < 0) == (float(r["ch"]) < 0)]
    grp = {"deeper": [r for r in ok if abs(float(r["ch"])) > abs(float(r["oh"]))],
           "shallower": [r for r in ok if abs(float(r["ch"])) < abs(float(r["oh"]))],
           "same": [r for r in ok if abs(float(r["ch"])) == abs(float(r["oh"]))]}
    print("样本", len(rows))
    for k, v in grp.items():
        print(k, _rate(v))
    big = [r for r in grp["deeper"] if abs(abs(float(r["ch"])) - abs(float(r["oh"]))) >= 0.49]
    print("deeper>=0.5", _rate(big))
    k = len(grp["deeper"]) // 3
    print("deeper 三等分", [_rate(grp["deeper"][i * k:(i + 1) * k if i < 2 else None]) for i in range(3)])
    hk = [r for r in rows if float(r["ch"]) != 0 and r["ho"] is not None and 0.4 <= float(r["ho"]) <= 1.4 and 0.4 <= float(r["ao"]) <= 1.4]
    for side in ("upper", "lower"):
        tot = n = 0
        for r in hk:
            o = _ah_outcome(int(r["hs"]), int(r["a"]), float(r["ch"]))
            if not o:
                continue
            uw, lw = (float(r["ho"]), float(r["ao"])) if float(r["ch"]) < 0 else (float(r["ao"]), float(r["ho"]))
            tot += _pnl(o[0], side, uw if side == "upper" else lw)
            n += 1
        print("无差别买", side, "ROI%", round(tot / n * 100, 1) if n else None, "n", n)


def water():
    """同盘口(开盘=终盘)上盘水位变动分组的上盘赢盘率与终盘价格 ROI。"""
    with get_db() as c:
        cur = c.cursor()
        cur.execute("""SELECT h.company, m.match_timestamp ts, m.home_score hs, m.away_score a, h.close_handicap ch,
                       h.open_home_odds oho, h.open_away_odds oao, h.close_home_odds cho, h.close_away_odds cao
                       FROM jczq_ah_history h JOIN matches m ON m.match_id=h.match_id
                       WHERE m.home_score IS NOT NULL AND h.close_handicap<>0 AND h.open_handicap=h.close_handicap
                       AND h.open_home_odds BETWEEN 0.4 AND 1.4 AND h.open_away_odds BETWEEN 0.4 AND 1.4
                       AND h.close_home_odds BETWEEN 0.4 AND 1.4 AND h.close_away_odds BETWEEN 0.4 AND 1.4""")
        rows = sorted(cur.fetchall(), key=lambda r: r["ts"] or 0)

    def d(r):
        ch = float(r["ch"])
        uo, uc = (float(r["oho"]), float(r["cho"])) if ch < 0 else (float(r["oao"]), float(r["cao"]))
        return uc - uo

    def roi(sel, side):
        tot = n = 0
        for r in sel:
            ch = float(r["ch"])
            o = _ah_outcome(int(r["hs"]), int(r["a"]), ch)
            if not o:
                continue
            uw, lw = (float(r["cho"]), float(r["cao"])) if ch < 0 else (float(r["cao"]), float(r["cho"]))
            tot += _pnl(o[0], side, uw if side == "upper" else lw)
            n += 1
        return (round(tot / n * 100, 1), n) if n else None

    grp = {"drop": [r for r in rows if d(r) < -0.05], "rise": [r for r in rows if d(r) > 0.05],
           "flat": [r for r in rows if abs(d(r)) <= 0.05]}
    print("同盘口水位变动 行数", len(rows))
    for k, v in grp.items():
        print(k, "上盘赢盘率/n", _rate(v))
    b5 = [r for r in rows if r["company"] == "Bet365-500"]
    print("Bet365-500 降水后买上盘 ROI", roi([r for r in b5 if d(r) < -0.05], "upper"),
          " 升水后买下盘 ROI", roi([r for r in b5 if d(r) > 0.05], "lower"))


if __name__ == "__main__":
    main()
    water()
