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
