"""开赛前同步间隔。"""
from scraper.sporttery_service import compute_sync_sleep, should_light_sync


def main() -> None:
    assert compute_sync_sleep(None) == 600
    assert compute_sync_sleep(2000) == 600
    assert compute_sync_sleep(700) == 600
    assert compute_sync_sleep(500) == 410
    assert compute_sync_sleep(90) == 45
    assert compute_sync_sleep(45) == 30
    assert compute_sync_sleep(20) == 8
    assert compute_sync_sleep(15) == 600
    assert compute_sync_sleep(10) == 600
    assert should_light_sync(400) is True
    assert should_light_sync(800) is False
    assert should_light_sync(None) is False
    print("ok sync sleep")


if __name__ == "__main__":
    main()


def test_tier_ttls_and_next_sleep() -> None:
    from scraper.sporttery_service import next_sync_sleep, tier_ttls
    assert tier_ttls(None) == (1200, 2700)
    assert tier_ttls(-5) == (3600, 7200)            # 已开赛: 最低频
    assert tier_ttls(900) == (240, 600)             # 30分钟内
    assert tier_ttls(2 * 3600) == (540, 1200)       # 3小时内约9分钟
    assert tier_ttls(8 * 3600) == (1200, 2700)
    assert tier_ttls(30 * 3600) == (3600, 7200)
    # 常规: 开始到开始, 扣掉耗时
    assert next_sync_sleep(None, 180) == 420
    assert next_sync_sleep(5 * 3600, 180) == 420
    assert next_sync_sleep(5 * 3600, 700) == 20      # 超时则只留下限
    # 开赛前30分钟内: 5分钟一轮
    assert next_sync_sleep(1500, 120) == 180
    assert next_sync_sleep(1000, 60) == 240
    # 更近: 沿用原绝对等待(不扣耗时)
    assert next_sync_sleep(500, 100) == 410
    assert next_sync_sleep(90, 30) == 45
    print("ok tier/next sleep")


if __name__ == "__main__":
    test_tier_ttls_and_next_sleep()


def test_due_tick_tasks() -> None:
    from scraper.sporttery_service import TICK_PLAN, due_tick_tasks
    n = len(TICK_PLAN)
    fetched, final = {}, set()
    assert due_tick_tasks("m", None, 1000, fetched, final) == []                 # 无开赛时间
    assert due_tick_tasks("m", 5 * 3600, 1000, fetched, final) == []            # 窗口外不抓
    assert len(due_tick_tasks("m", 2 * 3600, 1000, fetched, final)) == n        # 窗口内首次: 全抓
    for kind, cid, _ in TICK_PLAN:
        fetched[("m", kind, cid)] = 1000
    assert due_tick_tasks("m", 2 * 3600, 1000 + 600, fetched, final) == []      # 常规TTL内
    assert len(due_tick_tasks("m", 2 * 3600, 1000 + 1300, fetched, final)) == n  # 超过常规TTL
    assert len(due_tick_tasks("m", 1200, 1000 + 400, fetched, final)) == n      # 30分钟内TTL更短(300s)
    assert due_tick_tasks("m", 1200, 1000 + 200, fetched, final) == []
    # 开赛后: 收尾抓一次, 之后不再抓; 过久也不抓
    assert len(due_tick_tasks("m", -60, 5000, fetched, final)) == n
    final.add("m")
    assert due_tick_tasks("m", -60, 5000, fetched, final) == []
    assert due_tick_tasks("x", -2000, 5000, fetched, final) == []
    print("ok due ticks")


if __name__ == "__main__":
    test_due_tick_tasks()
