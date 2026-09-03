"""同赔排序: 同单关软加成 + 亚盘升降同向。"""
from jczq_similar_odds import (
    _ah_line_move,
    _ah_move_rank_boost,
    _find_similar,
    _single_rank_boost,
    AH_MOVE_OPP_BOOST,
    AH_MOVE_SAME_BOOST,
    SINGLE_SOFT_BOOST,
)


def test_single_boost_asymmetric():
    assert _single_rank_boost(True, True) == SINGLE_SOFT_BOOST
    assert _single_rank_boost(True, False) == 1.0
    assert _single_rank_boost(False, True) == 1.0
    assert _single_rank_boost(False, False) == 1.0


def test_ah_line_move_by_depth():
    assert _ah_line_move(-0.50, -0.75) == "up"
    assert _ah_line_move(-0.75, -0.50) == "down"
    assert _ah_line_move(-0.50, -0.50) == "flat"
    assert _ah_line_move(0.50, 0.75) == "up"
    assert _ah_line_move(None, -0.50) is None


def test_ah_move_boost():
    assert _ah_move_rank_boost("up", "up") == AH_MOVE_SAME_BOOST
    assert _ah_move_rank_boost("down", "down") == AH_MOVE_SAME_BOOST
    assert _ah_move_rank_boost("flat", "flat") == AH_MOVE_SAME_BOOST
    assert _ah_move_rank_boost("up", "down") == AH_MOVE_OPP_BOOST
    assert _ah_move_rank_boost("up", "flat") == 1.0
    assert _ah_move_rank_boost(None, "up") == 1.0


def _hist(mid, is_single, open_hc, close_hc):
    return {
        "match_id": mid,
        "match_date": "2025-03-01",
        "league_name": "英超",
        "home_team": "A",
        "away_team": "B",
        "home_score": 1,
        "away_score": 0,
        "is_single": is_single,
        "open_handicap": open_hc,
        "handicap": close_hc,
        "result": "H",
        "open_win": 1.50, "open_draw": 3.80, "open_loss": 6.00,
        "close_win": 1.45, "close_draw": 3.90, "close_loss": 6.20,
    }


def test_rank_prefers_same_single_and_same_line_move():
    pool = [
        _hist("serial_same_move", 0, -0.50, -0.75),
        _hist("single_opp_move", 1, -0.75, -0.50),
        _hist("single_same_move", 1, -0.50, -0.75),
    ]
    res = _find_similar(
        1.50, 3.80, 6.00, 1.45, 3.90, 6.20,
        0.03, pool_loader=lambda: pool,
        league="英超",
        ah_open=-0.50, ah_close=-0.75,
        is_single=True,
    )
    ids = [m["match_id"] for m in res["matches"]]
    assert ids[0] == "single_same_move"
    ranks = {m["match_id"]: m["rank_score"] for m in res["matches"]}
    assert ranks["single_same_move"] > ranks["serial_same_move"]
    assert ranks["single_same_move"] > ranks["single_opp_move"]


def test_non_single_query_does_not_boost_historical_single():
    pool = [
        _hist("serial_same_move", 0, -0.50, -0.75),
        _hist("single_same_move", 1, -0.50, -0.75),
    ]
    res = _find_similar(
        1.50, 3.80, 6.00, 1.45, 3.90, 6.20,
        0.03, pool_loader=lambda: pool,
        league="英超",
        ah_open=-0.50, ah_close=-0.75,
        is_single=False,
    )
    by_id = {m["match_id"]: m["similarity"] for m in res["matches"]}
    assert by_id["serial_same_move"] == by_id["single_same_move"]


if __name__ == "__main__":
    test_single_boost_asymmetric()
    test_ah_line_move_by_depth()
    test_ah_move_boost()
    test_rank_prefers_same_single_and_same_line_move()
    test_non_single_query_does_not_boost_historical_single()
    print("ok similar rank boost")
