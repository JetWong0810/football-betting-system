"""北单列表/数据页解析测试(固定样本, 不联网不连库)。python3 test_bd_service.py"""
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
import bd_service as b  # noqa: E402

FX = os.path.join(os.path.dirname(__file__), "fixtures")


def rd(n):
    return open(os.path.join(FX, n), encoding="utf-8").read()


def test_list():
    items = b.parse_bd_list(rd("bd_list_sample.html"))
    assert len(items) == 3
    a = items[0]
    assert a["matchId"] == "bd_1474022" and a["period"] == "26118" and a["league"] == "亚冠精英联赛"
    assert a["home"] == "纽卡斯尔喷气机" and a["away"] == "柏太阳神" and a["rq"] == "+1" and a["score"] == "1:2"
    from datetime import datetime, timedelta, timezone
    ko = datetime.fromtimestamp(a["kickoffTs"], timezone(timedelta(hours=8))).strftime("%Y-%m-%d %H:%M")
    assert ko == "2026-11-24 15:45", ko          # 取比赛时间而非投注截止时间 15:35


def test_fenxi():
    p = b.parse_fenxi(rd("bd_fenxi_sample.html"), "1474048")
    assert p["h2h"] == [] and len(p["homeRecent"]) == 10 and len(p["awayRecent"]) == 10
    r = p["homeRecent"][0]
    assert r["date"] == "2026-11-21" and r["home"] == "京都不死鸟" and r["score"] == "2-1" and r["handicapText"] == "受半球"
    assert all(x["date"] != "2026-11-24" or x["home"] != "京都不死鸟" or x["away"] != "浦项铁人" for x in p["homeRecent"])  # 排除本场
    assert p["homeFuture"][0]["date"] == "2026-11-28" and p["standings"]["home"]["总成绩"][7] == "7"


def test_blocked_detect():
    assert b.looks_blocked("<script>function a(){}</script>")
    assert not b.looks_blocked("x" * 5000)


if __name__ == "__main__":
    for n, f in list(globals().items()):
        if n.startswith("test_"):
            f()
            print("ok", n)
