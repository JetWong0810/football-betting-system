"""足彩网深盘简写必须能解析, 否则 ypdb 整页公司全丢。"""
from scraper.asian_bet365 import _parse_handicap_value
from scraper.zgzcw_fenxi import _clean_hc


def _val(text: str):
    return _parse_handicap_value(_clean_hc(text))


def test_zgzcw_deep_abbreviations():
    assert _val("两/两半") == 2.25
    assert _val("两半") == 2.5
    assert _val("两半/三") == 2.75
    assert _val("三球") == 3.0
    assert _val("三/三半") == 3.25
    assert _val("三半↑") == 3.5
    assert _val("三球半") == 3.5
    assert _val("受三/三半") == -3.25
    assert _val("四球") == 4.0


if __name__ == "__main__":
    test_zgzcw_deep_abbreviations()
    print("ok handicap map")
