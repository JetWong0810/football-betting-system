"""ypdb/bjop 解析回归: cid 必须整段相等; 公司名映射规范名。"""
from scraper.zgzcw_fenxi import (
    parse_bjop,
    parse_bsls,
    parse_dxdb,
    parse_ypdb_bet365,
    parse_ypdb_mainstream,
    parse_ypdb_zhishu,
)

YPDB_HTML = """
<table>
<tr>
<td>2</td><td><a href="/ypdb/zhishu?company_id=22">平*</a></td>
<td>1.00</td><td>平/半</td><td>0.83</td>
<td>0.93</td><td>半球</td><td>0.97</td>
</tr>
<tr>
<td>3</td><td><a href="/ypdb/zhishu?company_id=2">微信推荐</a></td>
<td>0.80</td><td>半球</td><td>1.00</td>
<td>0.80</td><td>半球</td><td>1.00</td>
</tr>
<tr>
<td>5</td><td><a href="/ypdb/zhishu?company_id=2">36*</a></td>
<td>0.97</td><td>平/半</td><td>0.87</td>
<td>0.92↓</td><td>半球↑</td><td>0.92↑</td>
</tr>
<tr>
<td>6</td><td><a href="/ypdb/zhishu?company_id=9">威*</a></td>
<td>0.95</td><td>平手</td><td>0.85</td>
<td>0.90</td><td>平/半</td><td>0.90</td>
</tr>
</table>
"""

BJOP_HTML = """
<table>
<tr>
<td>1</td><td>平均欧赔</td>
<td>3.13</td><td>3.28</td><td>2.27</td>
<td>3.68</td><td>3.37</td><td>2.05</td>
<td></td><td>25</td><td>28</td><td>46</td>
<td>0.95</td><td>0.94</td><td>0.95</td><td>0.95</td>
</tr>
<tr>
<td>2</td><td>官方(胜平负)</td>
<td>3.10</td><td>3.25</td><td>2.01</td>
<td>3.30</td><td>3.35</td><td>1.90</td>
<td></td><td>26</td><td>26</td><td>46</td>
<td>0.85</td><td>0.94</td><td>0.88</td><td>0.89</td>
</tr>
<tr>
<td>5</td><td><a href="/bjop/zhishu?company_id=22">平*</a></td>
<td>3.00</td><td>3.20</td><td>2.20</td>
<td>3.50</td><td>3.30</td><td>2.10</td>
<td></td><td>25</td><td>28</td><td>46</td>
<td>0.93</td><td>0.91</td><td>0.95</td><td>0.93</td>
</tr>
<tr>
<td>5</td><td><a href="/bjop/zhishu?company_id=2">36*</a></td>
<td>3.10</td><td>3.25</td><td>2.25</td>
<td>3.80↑</td><td>3.40↓</td><td>2.00</td>
<td></td><td>24.89</td><td>27.82</td><td>47.29</td>
<td>0.98</td><td>0.95</td><td>0.92</td><td>0.95</td>
</tr>
</table>
"""

BSLS_HTML = """
<table>
<tr><td>联赛</td><td>轮次</td><td>时间</td><td>主队</td><td>比分</td><td>客队</td><td>半场</td><td>终赔</td><td>终盘</td><td>盘路</td></tr>
<tr><td>法甲</td><td></td><td>26-9-4</td><td>图卢兹</td><td>VS</td><td>里尔</td><td></td><td></td><td>0.83受半球1.05</td><td></td></tr>
<tr><td>法甲</td><td>2</td><td>26-8-30</td><td>布雷斯特</td><td>2:2</td><td>图卢兹</td><td>1:1</td><td></td><td>1.09平/半0.80</td><td>输</td></tr>
<tr><td>法甲</td><td>1</td><td>26-8-23</td><td>图卢兹</td><td>0:2</td><td>里昂</td><td>0:0</td><td></td><td>0.93平/半0.96</td><td>输</td></tr>
</table>
<table>
<tr><td>联赛</td><td>轮次</td><td>时间</td><td>主队</td><td>比分</td><td>客队</td><td>半场</td><td>终赔</td><td>终盘</td><td>盘路</td></tr>
<tr><td>法甲</td><td></td><td>26-9-4</td><td>图卢兹</td><td>VS</td><td>里尔</td><td></td><td></td><td></td><td></td></tr>
<tr><td>法甲</td><td>2</td><td>26-8-29</td><td>里尔</td><td>2:2</td><td>巴黎圣曼</td><td>1:0</td><td></td><td>0.95受半/一0.94</td><td>赢</td></tr>
</table>
<table>
<tr><td>联赛</td><td>轮次</td><td>时间</td><td>主队</td><td>比分</td><td>客队</td><td>半场</td><td>终赔</td><td>终盘</td><td>盘路</td></tr>
<tr><td>法甲</td><td>29</td><td>26-4-12</td><td>图卢兹</td><td>0:4</td><td>里尔</td><td>0:1</td><td></td><td>0.93受平/半0.95</td><td>输</td></tr>
<tr><td>法甲</td><td>4</td><td>25-9-14</td><td>里尔</td><td>2:1</td><td>图卢兹</td><td>0:0</td><td></td><td>0.88半球1.01</td><td>赢</td></tr>
</table>
<table>
<tr><td>联赛</td><td>轮次</td><td>时间</td><td>主队</td><td>比分</td><td>客队</td><td>半场</td></tr>
<tr><td>法甲</td><td>4</td><td>2026-09-13</td><td>洛里昂</td><td>VS</td><td>图卢兹</td><td>-</td></tr>
</table>
<table>
<tr><td>联赛</td><td>轮次</td><td>时间</td><td>主队</td><td>比分</td><td>客队</td><td>半场</td></tr>
<tr><td>欧冠</td><td></td><td>2026-09-09</td><td>里尔</td><td>VS</td><td>贝蒂斯</td><td>-</td></tr>
</table>
"""

DXDB_HTML = """
<table>
<tr>
<td>1</td><td>平均*</td>
<td>0.90</td><td>2.5球</td><td>0.90</td>
<td>0.88</td><td>2.5球</td><td>0.92</td>
</tr>
<tr>
<td>2</td><td><a href="/dxdb/zhishu?company_id=22">平*</a></td>
<td>0.90</td><td>2.5球</td><td>0.90</td>
<td>0.85</td><td>2.5球</td><td>0.95</td>
</tr>
<tr>
<td>5</td><td><a href="/dxdb/zhishu?company_id=2">36*</a></td>
<td>0.85</td><td>2/2.5球</td><td>0.95</td>
<td>0.88↓</td><td>2.5球↑</td><td>0.92↑</td>
</tr>
<tr>
<td>6</td><td><a href="/dxdb/zhishu?company_id=9">威*</a></td>
<td>0.80</td><td>2.5/3球</td><td>1.00</td>
<td>0.82</td><td>2.5球</td><td>0.98</td>
</tr>
</table>
"""

ZHISHU_HTML = """
<table>
<tr><td>序号</td><td>时间</td><td>更新</td><td>主</td><td>盘口</td><td>客</td></tr>
<tr><td>1</td><td>2026-09-03 12:23:59</td><td>即时</td><td>1↓</td><td>平手</td><td>0.8↑</td></tr>
<tr><td>2</td><td>2026-09-03 11:00:00</td><td></td><td>0.95</td><td>平/半</td><td>0.85</td></tr>
<tr><td>3</td><td>2026-09-03 10:00:00</td><td>初盘</td><td>0.9</td><td>平手</td><td>0.9</td></tr>
</table>
"""


def main() -> None:
    line = parse_ypdb_bet365(YPDB_HTML)
    assert line is not None, "应命中 cid=2"
    assert line["name"] == "36*", line
    assert abs(line["open_home"] - 0.97) < 1e-9, line
    assert abs(line["close_hc"] - 0.5) < 1e-9, line
    books = {c["bookmaker"]: c for c in parse_ypdb_mainstream(YPDB_HTML)}
    assert "Bet365" in books and "Pinnacle" in books and "威廉希尔" in books, books.keys()
    assert books["Pinnacle"]["current"]["handicap"] == 0.5

    euro = parse_bjop(BJOP_HTML)
    names = [c["bookmaker"] for c in euro["companies"]]
    assert names == ["竞彩官方", "Pinnacle", "Bet365"], names
    b365 = next(c for c in euro["companies"] if c["bookmaker"] == "Bet365")
    assert abs(b365["current"]["win"] - 3.80) < 1e-9
    assert abs(b365["returnRate"] - 95.0) < 1e-9
    assert b365["kelly"]["win"] == 0.98

    form = parse_bsls(BSLS_HTML)
    assert form["homeTeamName"] == "图卢兹", form["homeTeamName"]
    assert form["awayTeamName"] == "里尔", form["awayTeamName"]
    assert len(form["homeRecent"]) == 2, form["homeRecent"]
    r0 = form["homeRecent"][0]
    assert r0["result"] == "平" and r0["match"] == "布雷斯特2:2图卢兹", r0
    # 盘路为历史主队视角, 焦点图卢兹为客 → 翻
    assert r0["asianResult"] == "赢", r0
    r1 = form["homeRecent"][1]
    assert r1["result"] == "负" and r1["asianResult"] == "输", r1
    a0 = form["awayRecent"][0]
    assert a0["result"] == "平" and a0["asianResult"] == "赢", a0
    assert form["h2h"][0]["asianResult"] == "输", form["h2h"][0]
    # 里尔主场半球赢 → 当前主队图卢兹客场翻成输
    assert form["h2h"][1]["asianResult"] == "输", form["h2h"][1]
    assert form["h2h"][1]["handicap"] == "0.5", form["h2h"][1]
    assert form["homeFuture"] and "洛里昂" in form["homeFuture"][0]["match"]

    ou = parse_dxdb(DXDB_HTML)
    books = {c["bookmaker"]: c for c in ou}
    assert "Bet365" in books and "Pinnacle" in books and "威廉希尔" in books, books.keys()
    assert abs(books["Bet365"]["initial"]["line"] - 2.25) < 1e-9, books["Bet365"]
    assert abs(books["Bet365"]["current"]["line"] - 2.5) < 1e-9
    assert abs(books["威廉希尔"]["initial"]["line"] - 2.75) < 1e-9
    assert books["Bet365"]["cid"] == 2

    ticks = parse_ypdb_zhishu(ZHISHU_HTML)
    assert len(ticks) == 3, ticks
    assert ticks[0]["time"].startswith("2026-09-03 12:23")
    assert abs(ticks[0]["home"] - 1.0) < 1e-9
    assert ticks[0]["handicapText"] == "平手"
    assert abs(ticks[1]["handicap"] - 0.25) < 1e-9
    assert abs(ticks[-1]["home"] - 0.9) < 1e-9
    print("ok ypdb/bjop/bsls/dxdb/zhishu")


if __name__ == "__main__":
    main()
