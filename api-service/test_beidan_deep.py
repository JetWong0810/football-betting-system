"""北单初盘 1.5 vs 市场 0.75≥30%。"""
from zgzcw_cache import is_beidan_deep, split_asian_blob


def _c(hc):
    return {"bookmaker": "Bet365", "initial": {"handicap": hc}}


def test_beidan_deep_trigger():
    companies = [_c(0.75), _c(0.75), _c(1.0), _c(-0.75), _c(1.0), _c(0.75), _c(-1.0)]
    beidan = {"bookmaker": "北单", "initial": {"handicap": 1.5}}
    assert is_beidan_deep(companies, beidan)
    assert is_beidan_deep(companies, {"initial": {"handicap": -1.5}})


def test_beidan_deep_skip():
    companies = [_c(0.75), _c(1.0), _c(1.0), _c(1.0)]
    assert not is_beidan_deep(companies, {"initial": {"handicap": 1.5}})
    assert not is_beidan_deep(companies, {"initial": {"handicap": 0.75}})
    assert not is_beidan_deep(companies, None)
    assert not is_beidan_deep([], {"initial": {"handicap": 1.5}})


def test_split_asian_blob_keeps_beidan():
    companies, beidan = split_asian_blob({
        "companies": [_c(0.75)],
        "beidan": {"cid": 88, "initial": {"handicap": 1.5}},
    })
    assert len(companies) == 1
    assert beidan["bookmaker"] == "北单"
    assert beidan["initial"]["handicap"] == 1.5
    companies, beidan = split_asian_blob([_c(0.75)])
    assert beidan is None and len(companies) == 1


if __name__ == "__main__":
    test_beidan_deep_trigger()
    test_beidan_deep_skip()
    test_split_asian_blob_keeps_beidan()
    print("ok beidan deep")
