"""zgzcw fid: 首页场次号 / 投注页队ID / 全量页队名。"""
from scraper.zgzcw_live import (
    match_zgzcw_fids,
    parse_betting_matches,
    parse_live_code_map,
    parse_qb_fixtures,
)

LIVE_HTML = """
<table>
<tr class="matchTr" matchid="4566612">
<td>周五001</td><td>德乙</td><td></td><td></td><td>完</td>
<td>0 [13] 汉诺威 ( -1 )</td><td>2-2</td>
<td>卡斯鲁厄 [8] 0</td>
</tr>
</table>
"""

QB_HTML = """
<table>
<tr class="matchTr" matchid="4555217">
<td></td>
<td>日职联</td>
<td>第6轮</td>
<td class="matchDate" date="2026-09-05 18:00:00">09-05 18:00</td>
<td>未</td>
<td><em class="paim">[18]</em>
<a href="http://saishi.zgzcw.com/soccer/team/567/10898">福冈黄蜂</a></td>
<td>-</td>
<td><a href="http://saishi.zgzcw.com/soccer/team/567/15733">水户蜀葵</a>
<em class="paim">[7]</em></td>
</tr>
<tr class="matchTr" matchid="4566229">
<td></td>
<td>德甲</td>
<td></td>
<td class="matchDate" date="2026-09-05 21:30:00">09-05 21:30</td>
<td>未</td>
<td><em class="paim">[12]</em>
<a href="http://saishi.zgzcw.com/soccer/team/1/20001">门兴</a></td>
<td>-</td>
<td><a href="http://saishi.zgzcw.com/soccer/team/1/20002">埃弗斯堡</a>
<em class="paim">[16]</em></td>
</tr>
</table>
"""

BET_HTML = """
<table>
<tr class="beginBet">
<td><a href="javascript:void(0);" id="show_2041267" class="ah">
<code style="display:none">周六</code><i>001</i></a></td>
<td>日职联</td>
<td><span title="比赛时间:2026-09-05 18:00">18:00</span></td>
<td><a href="http://saishi.zgzcw.com/soccer/team/567/10898">福冈黄蜂</a>
<em class="pm">[18]</em></td>
<td>VS</td>
<td><em class="pm">[7]</em>
<a href="http://saishi.zgzcw.com/soccer/team/567/15733">水户蜀葵</a></td>
</tr>
<tr class="beginBet">
<td><a href="javascript:void(0);" id="show_2041273" class="ah">
<code style="display:none">周六</code><i>007</i></a></td>
<td>德甲</td>
<td><span title="比赛时间:2026-09-05 21:30">21:30</span></td>
<td><a href="http://saishi.zgzcw.com/soccer/team/1/20001">门兴</a></td>
<td>VS</td>
<td><a href="http://saishi.zgzcw.com/soccer/team/1/20002">埃弗斯堡</a></td>
</tr>
</table>
"""


def test_parse_live_code_map():
    m = parse_live_code_map(LIVE_HTML)
    assert m["周五001"]["fid"] == "4566612"
    assert m["周五001"]["home_rank"] == "13"
    assert m["周五001"]["away_rank"] == "8"


def test_parse_qb_and_bet():
    qb = parse_qb_fixtures(QB_HTML)
    assert {r["fid"] for r in qb} == {"4555217", "4566229"}
    fukuoka = next(r for r in qb if r["fid"] == "4555217")
    assert fukuoka["home_tid"] == "10898" and fukuoka["away_tid"] == "15733"
    assert fukuoka["home_rank"] == "18" and fukuoka["away_rank"] == "7"

    bet = parse_betting_matches(BET_HTML)
    assert bet["2041267"]["home_tid"] == "10898"
    assert bet["2041267"]["match_code"] == "周六001"
    assert bet["2041273"]["away_tid"] == "20002"


def test_match_prefers_live_code():
    live = [{
        "match_id": "1", "match_code": "周五001",
        "match_date": "2026-09-05", "home_team_name": "汉诺威",
        "away_team_name": "卡斯鲁厄",
    }]
    out = match_zgzcw_fids(
        live, parse_live_code_map(LIVE_HTML), {}, parse_qb_fixtures(QB_HTML),
    )
    assert out["1"]["fid"] == "4566612"
    assert out["1"]["source"] == "live"


def test_match_qb_by_team_id_ignores_name_diff():
    live = [{
        "match_id": "2041273", "match_code": "周六007",
        "match_date": "2026-09-05",
        "home_team_name": "门兴", "away_team_name": "埃沃斯堡",
    }]
    out = match_zgzcw_fids(
        live, {}, parse_betting_matches(BET_HTML), parse_qb_fixtures(QB_HTML),
    )
    assert out["2041273"]["fid"] == "4566229"
    assert out["2041273"]["source"] == "qb"


def test_match_name_fallback_without_betting():
    live = [{
        "match_id": "2041267", "match_code": "周六001",
        "match_date": "2026-09-05",
        "home_team_name": "福冈黄蜂", "away_team_name": "水户蜀葵",
    }]
    out = match_zgzcw_fids(live, {}, {}, parse_qb_fixtures(QB_HTML))
    assert out["2041267"]["fid"] == "4555217"
    assert out["2041267"]["source"] == "name"


def test_keeps_existing_db_fid_if_unmapped():
    live = [{
        "match_id": "x", "match_code": "周一009",
        "match_date": "2026-09-08", "fid_zgzcw": "999",
        "home_team_name": "维多利亚", "away_team_name": "格雷米奥",
    }]
    out = match_zgzcw_fids(live, {}, {}, parse_qb_fixtures(QB_HTML))
    assert out["x"]["fid"] == "999"
    assert out["x"]["source"] == "db"
