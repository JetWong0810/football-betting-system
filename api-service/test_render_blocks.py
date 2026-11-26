"""集成回归: 真实库里取一场已抓到盘口的比赛, 断言盘口上下文里各附加块都在。
(曾因 import 顺序错误导致 try 里的块被静默吞掉而测试没发现。) 库里没有合适比赛则跳过。python3 test_render_blocks.py"""
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
from database import get_db  # noqa: E402
from match_chat.context import build_context  # noqa: E402

BLOCKS = ["【盘口读法】", "【赢盘基准】", "【同盘口历史净胜分布】", "【市场先验】", "【水位参考·亚盘】", "【最优价】", "【历史信号】"]


def main():
    with get_db() as c:
        cur = c.cursor()
        cur.execute("SELECT t.match_id FROM odds500_ah_ticks t JOIN bd_matches b ON b.match_id=t.match_id "
                    "WHERE t.company='Bet365' GROUP BY t.match_id HAVING COUNT(*)>=3 ORDER BY MAX(t.tick_time) DESC LIMIT 1")
        r = cur.fetchone()
    if not r:
        print("skip: 没有已抓取盘口的北单比赛")
        return
    text = build_context(r["match_id"])["text"]
    miss = [b for b in BLOCKS if b not in text]
    # 平手盘没有上下盘, 不要求同盘口分布里出现"让";只要求段落存在
    assert not miss, f"缺少: {miss}"
    print("ok render blocks", r["match_id"])


if __name__ == "__main__":
    main()
