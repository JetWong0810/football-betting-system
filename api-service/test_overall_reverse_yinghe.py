"""单关 + 共识一边倒 + 竞彩胜平负迎合 → 整体逆向。"""
from predict_service import calc_prediction, detect_spf_yinghe, FACTOR_WEIGHTS

NAMES = list(FACTOR_WEIGHTS.keys())


def _factors(dirs, scores=None):
    scores = scores or [7] * 7
    return [
        {"name": n, "score": scores[i], "direction": dirs[i], "reason": "t"}
        for i, n in enumerate(NAMES)
    ]


def _spf(win_open, win_close, lose_open=4.20, lose_close=4.20):
    return {
        "initial": {"win": win_open, "draw": 3.30, "lose": lose_open},
        "current": {"win": win_close, "draw": 3.30, "lose": lose_close},
    }


def _ctx(is_single, spf, home_is_upper=True):
    return {"is_single": is_single, "spf_odds": spf, "home_is_upper": home_is_upper}


ALL_UPPER = ["upper"] * 7
ALL_LOWER = ["lower"] * 7


def test_yinghe_upper_home_let_win_drop():
    hit = detect_spf_yinghe(_spf(1.50, 1.40), "upper", True)
    assert hit["hit"] is True
    assert hit["label"] == "主胜"
    assert hit["delta"] == -0.10


def test_yinghe_lower_home_let_win_rise():
    hit = detect_spf_yinghe(_spf(1.50, 1.60), "lower", True)
    assert hit["hit"] is True
    assert hit["delta"] == 0.10


def test_yinghe_upper_away_let_lose_drop():
    hit = detect_spf_yinghe(_spf(2.80, 2.80, 1.55, 1.42), "upper", False)
    assert hit["hit"] is True
    assert hit["label"] == "客胜"


def test_yinghe_flat_not_hit():
    hit = detect_spf_yinghe(_spf(1.50, 1.49), "upper", True)
    assert hit["hit"] is False


def test_single_consensus_yinghe_reverses_to_lower():
    """例1: 主上盘, 因子看好上盘, 主胜下降, 单关 → 下盘。"""
    pred = calc_prediction(
        _factors(ALL_UPPER), FACTOR_WEIGHTS,
        reverse_ctx=_ctx(True, _spf(1.45, 1.35)),
    )
    assert pred["overall_reverse"] is True
    assert pred["direction"] == "lower"
    assert pred["consensus_dir"] == "upper"
    assert pred["yinghe"]["hit"] is True
    assert "主胜" in pred["reverse_reason"]


def test_single_consensus_yinghe_reverses_to_upper():
    """例2: 因子看好下盘, 主胜上升, 单关 → 上盘。"""
    pred = calc_prediction(
        _factors(ALL_LOWER), FACTOR_WEIGHTS,
        reverse_ctx=_ctx(True, _spf(1.45, 1.58)),
    )
    assert pred["overall_reverse"] is True
    assert pred["direction"] == "upper"
    assert pred["consensus_dir"] == "lower"


def test_not_single_no_overall_reverse():
    pred = calc_prediction(
        _factors(ALL_UPPER), FACTOR_WEIGHTS,
        reverse_ctx=_ctx(False, _spf(1.45, 1.35)),
    )
    assert pred["overall_reverse"] is False
    assert pred["direction"] == "upper"


def test_single_but_odds_not_yinghe_no_reverse():
    pred = calc_prediction(
        _factors(ALL_UPPER), FACTOR_WEIGHTS,
        reverse_ctx=_ctx(True, _spf(1.45, 1.45)),
    )
    assert pred["overall_reverse"] is False
    assert pred["direction"] == "upper"


def test_wc_legacy_still_reverses_without_ctx():
    pred = calc_prediction(_factors(ALL_UPPER), FACTOR_WEIGHTS)
    assert pred["overall_reverse"] is True
    assert pred["direction"] == "lower"
    assert pred["yinghe"] is None


def test_heat_already_flipped_no_double_reverse():
    """热度/单关高强度逆向已把加权翻离共识时, 不再整体再翻。"""
    scores = [6, 6, 6, 10, 6, 6, 10]
    pred = calc_prediction(
        _factors(ALL_UPPER, scores), FACTOR_WEIGHTS,
        reverse_ctx=_ctx(True, _spf(1.45, 1.35)),
    )
    assert pred["direction"] == "lower"
    assert pred["overall_reverse"] is False


if __name__ == "__main__":
    test_yinghe_upper_home_let_win_drop()
    test_yinghe_lower_home_let_win_rise()
    test_yinghe_upper_away_let_lose_drop()
    test_yinghe_flat_not_hit()
    test_single_consensus_yinghe_reverses_to_lower()
    test_single_consensus_yinghe_reverses_to_upper()
    test_not_single_no_overall_reverse()
    test_single_but_odds_not_yinghe_no_reverse()
    test_wc_legacy_still_reverses_without_ctx()
    test_heat_already_flipped_no_double_reverse()
    print("ok overall reverse yinghe")
