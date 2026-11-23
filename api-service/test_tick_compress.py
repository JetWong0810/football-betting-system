from match_chat.context import compress_ticks


def _ah(hs):
    return [{"time": f"t{i}", "handicap": h} for i, h in enumerate(hs)]


def test_asian_keeps_line_changes():
    r = compress_ticks("asian", _ah([0.5, 0.5, 0.5, 0.75, 0.75, 0.5, 0.5, 0.75]))
    assert [t["time"] for t in r] == ["t0", "t3", "t5", "t7"]


def test_ou_flat_collapses_to_ends():
    assert len(compress_ticks("ou", [{"time": f"t{i}", "line": 2.5} for i in range(30)])) == 2


def test_cap_keeps_first_and_latest():
    r = compress_ticks("ou", [{"time": f"t{i}", "line": i} for i in range(30)])
    assert len(r) == 12 and r[0]["time"] == "t0" and r[-1]["time"] == "t29"


def test_euro_threshold_1pp():
    eu = [{"time": "a", "win": 2.0, "draw": 3.4, "lose": 3.6}, {"time": "b", "win": 2.01, "draw": 3.4, "lose": 3.6},
          {"time": "c", "win": 1.85, "draw": 3.5, "lose": 4.2}, {"time": "d", "win": 1.85, "draw": 3.5, "lose": 4.2}]
    assert [t["time"] for t in compress_ticks("euro", eu)] == ["a", "c", "d"]
