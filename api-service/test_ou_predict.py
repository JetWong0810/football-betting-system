"""大小球预测 O1-O5 单测, 不连库。"""
from ou_predict_service import (
    DOWN,
    NEU,
    UP,
    calc_ou_heat,
    calc_ou_recent,
    calc_ou_signal,
    calc_ou_structure,
    calc_ou_ttg,
    pick_standard,
    predict_ou,
    settle_ou,
)


def _c(book, oline, cline, oover, cover, ounder=0.95, cunder=0.95):
    return {
        "bookmaker": book,
        "initial": {"line": oline, "over": oover, "under": ounder},
        "current": {"line": cline, "over": cover, "under": cunder},
    }


def test_settle_quarter():
    assert settle_ou(4, 2.75) == "over"
    assert settle_ou(3, 2.75) == "half_over"
    assert settle_ou(2, 2.75) == "under"
    assert settle_ou(3, 2.5) == "over"
    assert settle_ou(2, 2.5) == "under"
    assert settle_ou(3, 3.0) == "push"
    assert settle_ou(3, 2.25) == "over"
    assert settle_ou(2, 2.25) == "half_under"
    assert settle_ou(1, 2.25) == "under"


def test_o1_trap_over_to_under():
    # 升盘+大球升水 = 诱大 → 偏小
    data = [
        _c("Bet365", 2.75, 3.00, 0.85, 0.98),
        _c("Pinnacle", 2.75, 3.00, 0.86, 0.97),
        _c("皇冠", 2.75, 3.00, 0.84, 0.99),
    ]
    f = calc_ou_signal(data, 3.00)
    assert f["direction"] == DOWN, f
    assert f["score"] >= 7
    assert "诱大" in f["reason"]


def test_o1_trap_under_to_over():
    data = [
        _c("Bet365", 2.75, 2.50, 0.90, 0.80),
        _c("Pinnacle", 2.75, 2.50, 0.92, 0.78),
        _c("皇冠", 2.75, 2.50, 0.88, 0.82),
    ]
    f = calc_ou_signal(data, 2.50)
    assert f["direction"] == UP, f
    assert "诱小" in f["reason"]


def test_o1_true_upgrade_over():
    # 升盘但大球没升水 → 真升盘偏大
    data = [
        _c("Bet365", 2.50, 2.75, 0.90, 0.88),
        _c("Pinnacle", 2.50, 2.75, 0.92, 0.90),
        _c("皇冠", 2.50, 2.75, 0.91, 0.89),
        _c("威廉希尔", 2.50, 2.75, 0.90, 0.90),
    ]
    f = calc_ou_signal(data, 2.75)
    assert f["direction"] == UP, f
    assert "真升盘" in f["reason"]


def test_o1_365_alone_capped():
    data = [
        _c("Bet365", 2.50, 2.75, 0.90, 0.88),
        _c("Pinnacle", 2.50, 2.50, 0.90, 0.90),
        _c("皇冠", 2.50, 2.50, 0.90, 0.90),
    ]
    f = calc_ou_signal(data, 2.75)
    if f["direction"] != NEU:
        assert f["score"] <= 6
        assert "独走" in f["reason"]


def test_o2_heat_excludes_traps():
    data = [
        _c("Bet365", 2.50, 2.50, 0.90, 0.80),
        _c("Pinnacle", 2.50, 2.50, 0.92, 0.82),
        _c("皇冠", 2.50, 2.50, 0.88, 0.78),
        _c("威廉希尔", 2.50, 2.50, 0.91, 0.81),
        _c("澳门", 2.75, 3.00, 0.85, 0.98),  # 诱大, 不计热度
        _c("立博", 2.00, 2.00, 0.90, 0.90),  # 异盘
    ]
    f = calc_ou_heat(data, 2.50)
    assert f["direction"] == UP, f
    assert "大热" in f["reason"] or "大略热" in f["reason"]


def test_o2_moved_not_in_heat():
    data = [
        _c("Bet365", 2.50, 2.75, 0.90, 0.80),
        _c("Pinnacle", 2.50, 2.75, 0.90, 0.82),
        _c("皇冠", 2.50, 2.75, 0.90, 0.78),
        _c("威廉希尔", 2.50, 2.75, 0.90, 0.81),
    ]
    f = calc_ou_heat(data, 2.75)
    assert f["direction"] == NEU, f
    assert "调盘不计" in f["reason"]


def test_o3_365_deeper_under():
    std = _c("Bet365", 2.50, 3.00, 0.90, 0.90)
    data = [
        std,
        _c("Pinnacle", 2.50, 2.50, 0.90, 0.90),
        _c("皇冠", 2.50, 2.50, 0.90, 0.90),
        _c("威廉希尔", 2.50, 2.50, 0.90, 0.90),
    ]
    f = calc_ou_structure(data, std, "Bet365")
    assert f["direction"] == DOWN, f
    assert f["score"] >= 7


def test_o3_wide_spread_neutral_penalty():
    std = _c("Bet365", 2.50, 2.75, 0.90, 0.90)
    data = [
        std,
        _c("Pinnacle", 2.50, 2.75, 0.90, 0.90),
        _c("立博", 2.50, 3.75, 0.90, 0.90),
        _c("韦德", 2.50, 2.50, 0.90, 0.90),
    ]
    f = calc_ou_structure(data, std, "Bet365")
    assert f["direction"] == NEU
    assert f["confidencePenalty"] >= 8


def test_o4_recent_over():
    form = {
        "homeTeamName": "主队",
        "awayTeamName": "客队",
        "homeRecent": [
            {"match": f"主队{s}客队"} for s in ("3:2", "2:2", "4:1", "2:1", "3:1")
        ],
        "awayRecent": [
            {"match": f"甲{s}客队"} for s in ("2:2", "1:3", "2:1", "3:2", "1:2")
        ],
    }
    f = calc_ou_recent(form, 2.5)
    assert f["direction"] == UP, f
    assert f["sample"] >= 10


def test_o5_ttg_high_over():
    rows = [
        {"goal_range": "0", "min_goals": 0, "max_goals": 0, "odds": 8.0},
        {"goal_range": "1", "min_goals": 1, "max_goals": 1, "odds": 5.0},
        {"goal_range": "2", "min_goals": 2, "max_goals": 2, "odds": 3.5},
        {"goal_range": "3", "min_goals": 3, "max_goals": 3, "odds": 2.2},
        {"goal_range": "4", "min_goals": 4, "max_goals": 4, "odds": 4.0},
    ]
    f = calc_ou_ttg(rows, 2.5)
    assert f["direction"] == UP, f


def test_o5_ttg_far_only_penalty():
    rows = [
        {"goal_range": "7+", "min_goals": 7, "max_goals": 8, "odds": 1.8},
        {"goal_range": "2", "min_goals": 2, "max_goals": 2, "odds": 4.0},
    ]
    f = calc_ou_ttg(rows, 2.5)
    assert f["direction"] == NEU
    assert f["confidencePenalty"] >= 6


def test_heat_reverse_in_predict():
    # 全员同盘降水=大热, 合成应翻成偏小
    data = [
        _c("Bet365", 2.50, 2.50, 0.92, 0.80),
        _c("Pinnacle", 2.50, 2.50, 0.90, 0.82),
        _c("皇冠", 2.50, 2.50, 0.91, 0.78),
        _c("威廉希尔", 2.50, 2.50, 0.93, 0.81),
        _c("澳门", 2.50, 2.50, 0.90, 0.80),
        _c("立博", 2.50, 2.50, 0.89, 0.79),
    ]
    out = predict_ou(data, form=None, ttg_rows=None)
    heat = next(f for f in out["factors"] if f["name"] == "市场热度")
    assert heat["direction"] == UP
    # 热度逆向后偏小; 其余因子中性 → 综合 lower
    assert out["prediction"]["direction"] == DOWN, out["prediction"]


def test_pick_bet365_standard():
    data = [_c("立博", 2.0, 2.0, 0.9, 0.9), _c("Bet365", 2.5, 2.75, 0.9, 0.88)]
    c, name = pick_standard(data)
    assert name == "Bet365"
    assert abs(c["current"]["line"] - 2.75) < 1e-9


if __name__ == "__main__":
    tests = [v for k, v in list(globals().items()) if k.startswith("test_")]
    for t in tests:
        t()
        print("ok", t.__name__)
    print("all", len(tests))
