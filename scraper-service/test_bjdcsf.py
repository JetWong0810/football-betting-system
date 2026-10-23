from scraper.bjdcsf import match_sfgg, parse_bjdcsf, to_beidan

HTML = """
<table>
<tr mid="52" rq="1.5" gdate="2026-10-23" fid="1425781"
    homesxname="博尔顿" awaysxname="米德尔斯堡" isend="0">
  <td>52</td>
</tr>
<tr mid="1" rq="-0.5" gdate="2026-10-23" fid="1450899"
    homesxname="布里斯班狮吼" awaysxname="珀斯光荣">
  <td>1</td>
</tr>
</table>
"""


def main() -> None:
    rows = parse_bjdcsf(HTML)
    assert len(rows) == 2, rows
    bolton = next(r for r in rows if r["fid"] == "1425781")
    assert bolton["rq"] == 1.5
    assert bolton["home"] == "博尔顿"
    hit = match_sfgg(
        {"fid_500": "1425781", "home_team_name": "博尔顿", "away_team_name": "米堡",
         "match_date": "2026-10-24"},
        rows,
    )
    assert hit and hit["rq"] == 1.5, hit
    hit2 = match_sfgg(
        {"home_team_name": "博尔顿", "away_team_name": "米堡", "match_date": "2026-10-23"},
        rows,
    )
    assert hit2 and hit2["fid"] == "1425781", hit2
    bd = to_beidan(bolton)
    assert bd["bookmaker"] == "北单" and bd["initial"]["handicap"] == 1.5
    print("ok bjdcsf")


if __name__ == "__main__":
    main()
