"""ypdb 解析回归: company_id=22 不得命中 cid=2。"""
from scraper.zgzcw_fenxi import parse_ypdb_bet365

HTML = """
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
</table>
"""


def main() -> None:
    line = parse_ypdb_bet365(HTML)
    assert line is not None, "应命中 cid=2"
    assert line["name"] == "36*", line
    assert abs(line["open_home"] - 0.97) < 1e-9, line
    assert abs(line["close_hc"] - 0.5) < 1e-9, line
    print("ok", line["name"], line["open_hc"], "->", line["close_hc"])


if __name__ == "__main__":
    main()
