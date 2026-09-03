"""官方凯利偏离: 只展示, 不进因子。"""
from predict_service import build_kelly_hint

EURO = {
    "companies": [
        {"bookmaker": "竞彩官方", "kelly": {"win": 0.91, "draw": 0.88, "lose": 0.87}},
        {"bookmaker": "威廉希尔", "kelly": {"win": 0.90, "draw": 0.84, "lose": 0.90}},
        {"bookmaker": "伟德", "kelly": {"win": 0.93, "draw": 0.93, "lose": 0.90}},
        {"bookmaker": "Bet365", "kelly": {"win": 0.86, "draw": 0.96, "lose": 0.93}},
        {"bookmaker": "立博", "kelly": {"win": 0.93, "draw": 0.93, "lose": 0.96}},
        {"bookmaker": "澳门", "kelly": {"win": 0.87, "draw": 0.94, "lose": 0.87}},
    ]
}


def test_thursday_sample_flags_tight_away_or_draw():
    hint = build_kelly_hint(EURO)
    assert hint, hint
    by_key = {i["key"]: i for i in hint["items"]}
    assert by_key["win"]["tag"] == ""
    assert by_key["draw"]["tag"] == "偏紧"
    assert by_key["lose"]["tag"] == "偏紧"
    assert hint["flagged"] is True
    assert hint["headline"].startswith("官方")
    assert "偏紧" in hint["headline"]
    assert "Bet365" in hint["books"] and "竞彩官方" not in hint["books"]


def test_loose_win_is_yinghe():
    data = {
        "companies": [
            {"bookmaker": "竞彩官方", "kelly": {"win": 1.05, "draw": 0.90, "lose": 0.90}},
            {"bookmaker": "Bet365", "kelly": {"win": 0.90, "draw": 0.90, "lose": 0.90}},
            {"bookmaker": "威廉希尔", "kelly": {"win": 0.88, "draw": 0.91, "lose": 0.92}},
        ]
    }
    hint = build_kelly_hint(data)
    assert hint["flagged"]
    assert hint["lean"] == "win"
    assert "偏松" in hint["headline"] and "主胜" in hint["headline"]


def test_missing_official_returns_none():
    data = {"companies": [
        {"bookmaker": "Bet365", "kelly": {"win": 0.9, "draw": 0.9, "lose": 0.9}},
        {"bookmaker": "威廉希尔", "kelly": {"win": 0.9, "draw": 0.9, "lose": 0.9}},
    ]}
    assert build_kelly_hint(data) is None


def test_close_to_mainstream_not_flagged():
    data = {
        "companies": [
            {"bookmaker": "竞彩官方", "kelly": {"win": 0.90, "draw": 0.90, "lose": 0.90}},
            {"bookmaker": "Bet365", "kelly": {"win": 0.91, "draw": 0.89, "lose": 0.90}},
            {"bookmaker": "威廉希尔", "kelly": {"win": 0.89, "draw": 0.91, "lose": 0.90}},
        ]
    }
    hint = build_kelly_hint(data)
    assert hint["flagged"] is False
    assert hint["headline"] == "官方凯利接近主流"


def test_zgzcw_cid_relabel_and_f3_excludes_weide():
    from zgzcw_cache import _normalize_companies
    from predict_service import _get_asian_companies

    rows = _normalize_companies([
        {"cid": 3, "bookmaker": "ＳＢ/*"},
        {"cid": 11, "bookmaker": "伟德"},
        {"cid": 2, "bookmaker": "Bet365"},
    ])
    by_cid = {r["cid"]: r["bookmaker"] for r in rows}
    assert by_cid[3] == "皇冠"
    assert by_cid[11] == "韦德"
    assert by_cid[2] == "Bet365"

    picked = [c["bookmaker"] for c in _get_asian_companies([
        {"bookmaker": "Bet365"},
        {"bookmaker": "韦德"},
        {"bookmaker": "皇冠"},
        {"bookmaker": "Pinnacle"},
    ])]
    assert picked == ["Pinnacle", "Bet365", "皇冠"]
    assert "韦德" not in picked
    assert "伟德" not in picked


if __name__ == "__main__":
    test_thursday_sample_flags_tight_away_or_draw()
    test_loose_win_is_yinghe()
    test_missing_official_returns_none()
    test_close_to_mainstream_not_flagged()
    test_zgzcw_cid_relabel_and_f3_excludes_weide()
    print("ok kelly hint")
