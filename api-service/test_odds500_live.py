"""实时抓取与聊天触发的单元测试(全 mock, 不联网、不碰数据库)。"""
import time
from datetime import datetime

import odds500_live as L
from match_chat import service as S


def test_wants_refresh():
    yes = ["抓取本场最新的盘口赔率数据并分析", "请刷新一下亚盘", "帮我拉取最新欧赔和大小球", "现在的盘口怎么样,最新变动"]
    no = ["首发出来了吗", "请关联本场盘口和赔率数据,分析矛盾", "三句话总结", "请继续", "为何进球方向偏大"]
    assert all(S.wants_refresh(t) for t in yes), [t for t in yes if not S.wants_refresh(t)]
    assert not any(S.wants_refresh(t) for t in no), [t for t in no if S.wants_refresh(t)]


def test_refresh_note_texts():
    ok = S.refresh_note({"ok": True, "fetchedAt": "2026-11-24 12:30:00", "got": 14, "failed": ["Pinnacle/ou"], "ticks": 30})
    assert "12-24" not in ok and "11-24 12:30" in ok and "1 项请求失败" in ok
    bad = S.refresh_note({"ok": False, "reason": "blocked"})
    assert "失败" in bad and "不是最新" in bad


class _Fake:
    requests = 0
    def __init__(self): self.calls = []
    def __enter__(self): return self
    def __exit__(self, *a): pass
    def allow(self): return True
    def fetch_fid_list(self, d):
        return {"周二001": {"fid": "F1", "kickoff": datetime(2026, 11, 24, 15, 45), "home": "x"}}
    def fetch_history(self, kind, fid, cid, ko):
        self.calls.append((kind, cid)); self.requests += 1
        if (kind, cid) == ("ou", 3): return None
        return [{"time": datetime(2026, 11, 24, 12, 0)}] if cid != 122 else []


def _patch(monkey):
    L._recent.clear(); L._calls.clear(); L._fid_lists.clear()
    ko = datetime(2026, 11, 24, 15, 45).timestamp() - 8 * 3600 + 0   # 仅占位, 下面覆盖 _load_match
    fake = _Fake()
    saves = []
    monkey["_load_match"] = L._load_match; monkey["ensure_tables"] = L.ensure_tables
    monkey["_save"] = L._save; monkey["Client"] = L.Odds500Client
    L._load_match = lambda mid: {"match_id": mid, "match_code": "周二001", "match_number": "261124",
                                 "match_timestamp": datetime(2026, 11, 24, 7, 45).timestamp() + time.timezone * 0 + 0}
    L.ensure_tables = lambda: None
    L._save = lambda kind, mid, rows, company, cid: saves.append((kind, company)) or len(rows)
    L.Odds500Client = lambda: fake
    return fake, saves


def _restore(m):
    L._load_match, L.ensure_tables, L._save, L.Odds500Client = m["_load_match"], m["ensure_tables"], m["_save"], m["Client"]


def test_refresh_flow_cooldown_and_partial_failure():
    m = {}
    fake, saves = _patch(m)
    try:
        # 开赛时间用当前时间 +1h, 保证不触发 too_old; fid 校验用列表页 kickoff 对不上会 mismatch, 所以对齐
        ts = time.time() + 3600
        L._load_match = lambda mid: {"match_id": mid, "match_code": "周二001", "match_number": "261124", "match_timestamp": ts}
        fake.fetch_fid_list = lambda d: {"周二001": {"fid": "F1", "kickoff": datetime.fromtimestamp(ts, L._BJ).replace(tzinfo=None), "home": "x"}}
        r = L.refresh_match_odds("m1")
        assert r["ok"] and r["got"] == 14 and r["failed"] == ["Bet365/ou"] and not r.get("cached")
        assert len(fake.calls) == 15 and fake.calls[0] == ("asian", 122)          # 香港马会优先
        assert all(c != "香港马会" for _, c in saves)                              # 无数据(空)不写库
        r2 = L.refresh_match_odds("m1")
        assert r2["cached"] and len(fake.calls) == 15                            # 冷却期内复用, 不再请求
    finally:
        _restore(m)


def test_kickoff_mismatch_and_rate_limit():
    m = {}
    fake, saves = _patch(m)
    try:
        ts = time.time() + 3600
        L._load_match = lambda mid: {"match_id": mid, "match_code": "周二001", "match_number": "261124", "match_timestamp": ts}
        r = L.refresh_match_odds("m2")           # 列表页 kickoff(2026-11-24 15:45) 与 ts 不一致
        assert not r["ok"] and r["reason"] == "kickoff_mismatch" and not fake.calls
        L._calls[:] = [time.time()] * L.HOURLY_CAP
        assert L.refresh_match_odds("m3")["reason"] == "rate_limited"
    finally:
        _restore(m)


if __name__ == "__main__":
    for n, f in list(globals().items()):
        if n.startswith("test_"):
            f(); print("ok", n)
