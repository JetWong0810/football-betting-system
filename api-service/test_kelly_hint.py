"""足彩网公司映射: 沙巴=皇冠, 韦德不进 F3。"""
from zgzcw_cache import _normalize_companies
from predict_service import _get_asian_companies


def test_zgzcw_cid_relabel_and_f3_excludes_weide():
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
    test_zgzcw_cid_relabel_and_f3_excludes_weide()
    print("ok zgzcw book mapping")
