import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
from match_chat.context import pick_ticks

def T(*times):
    return [{"time": t} for t in times]

KO = "2026-11-25 04:00:00"

def test_prefers_fresher_zgzcw():
    rows, src = pick_ticks(T("2026-11-24 20:00:00"), T("2026-11-24 23:00:00", "2026-11-24 10:00:00"), KO)
    assert src == "足彩网" and rows[0]["time"] == "2026-11-24 23:00:00"

def test_drops_inplay_zgzcw():
    rows, src = pick_ticks(T("2026-11-24 20:00:00"), T("2026-11-25 04:30:00", "2026-11-24 10:00:00"), KO)
    assert src == "500.com"

def test_tie_prefers_500():
    rows, src = pick_ticks(T("2026-11-24 20:00:00"), T("2026-11-24 20:00:00"), KO)
    assert src == "500.com"

def test_no_500_falls_back():
    rows, src = pick_ticks([], T("2026-11-25 05:00:00", "2026-11-24 10:00:00"), KO)
    assert src == "足彩网" and len(rows) == 1


if __name__ == "__main__":
    for k, v in list(globals().items()):
        if k.startswith("test_"):
            v()
    print("ok")
