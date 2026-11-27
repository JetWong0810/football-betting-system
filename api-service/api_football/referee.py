"""本场当值裁判: 从 API-Football 取名字, 给聊天的联网搜索用。

设计取舍(依据 2026-11 对本赛季 4930 场、94 位场次>=10 的裁判做的检验):
- 裁判在赛季内"前半程 vs 后半程"的稳定性(已扣除联赛差异): 黄牌/场 r≈+0.24~0.32(有一定个人倾向), 红牌 ≈0, 点球判罚 ≈0(-0.14~-0.01), 总进球 ≈0。
  75% 的裁判本赛季只有不到 5 场(中位数 2 场), 所以本系统自己的单裁判统计基本是噪音。
- 同一个裁判在库里有多种写法("A. Madley" / "Andrew Madley" / "Robert Madley, England"), 本系统不拿它做统计。
- 因此这里只提供"当值裁判是谁"和可靠性提醒, 风格、与两队渊源、倾向等深入分析交给联网搜索(更大样本、更长时间)。
"""
from __future__ import annotations

import logging
import re
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional

from database import get_db

from .client import AfClient
from .injuries import _kickoff, _mapping

logger = logging.getLogger(__name__)

TTL_ASSIGNED = 12 * 3600
TTL_PENDING = 30 * 60           # 还没公布: 临近开赛要尽快发现
TTL_NEAR = 20 * 60              # 开赛前后 3 小时内: 临场更换裁判要能尽快发现
_BJ = timezone(timedelta(hours=8))


def clean_name(raw: Optional[str]) -> Optional[str]:
    """去掉接口偶尔附带的国家后缀(如 'Felix Zwayer, Germany')。"""
    if not raw or not str(raw).strip():
        return None
    return re.sub(r"\s*,\s*[A-Za-z .\-']+$", "", str(raw).strip()) or None


def load_cached(match_id: str) -> Optional[Dict[str, Any]]:
    try:
        with get_db() as conn:
            cur = conn.cursor()
            cur.execute("SELECT referee, fetched_at FROM af_referee_cache WHERE match_id=%s", (match_id,))
            r = cur.fetchone()
    except Exception as e:  # noqa: BLE001
        if e.args and e.args[0] == 1146:
            return None
        raise
    return {"referee": r["referee"], "fetchedAt": r["fetched_at"]} if r else None


def fetch(match_id: str, force: bool = False, client: Optional[AfClient] = None) -> Dict[str, Any]:
    mp = _mapping(match_id)
    if not mp:
        return {"ok": False, "reason": "no_mapping"}
    cached = load_cached(match_id)
    if cached and not force:
        age = (datetime.utcnow() - cached["fetchedAt"]).total_seconds()
        ko = _kickoff(match_id)
        near = ko is not None and abs(ko - datetime.utcnow().replace(tzinfo=timezone.utc).timestamp()) <= 3 * 3600
        ttl = TTL_NEAR if near else (TTL_ASSIGNED if cached["referee"] else TTL_PENDING)
        if age < ttl:
            return {"ok": True, "cached": True, "referee": cached["referee"]}
    own = client is None
    c = client or AfClient()
    try:
        resp = c.get("/fixtures", {"id": mp["af_fixture_id"]}).get("response", [])
        name = clean_name(resp[0]["fixture"].get("referee")) if resp else None
        with get_db() as conn:
            conn.cursor().execute(
                "INSERT INTO af_referee_cache (match_id, af_fixture_id, referee) VALUES (%s,%s,%s) "
                "ON DUPLICATE KEY UPDATE af_fixture_id=VALUES(af_fixture_id), referee=VALUES(referee), fetched_at=CURRENT_TIMESTAMP",
                (match_id, mp["af_fixture_id"], name))
        return {"ok": True, "cached": False, "referee": name}
    except Exception as e:  # noqa: BLE001
        logger.warning("裁判查询失败 %s: %s", match_id, e)
        return {"ok": False, "reason": "error"}
    finally:
        if own:
            c.close()


RELIABILITY = ("可靠性提醒(本系统对本赛季 94 位场次≥10 的裁判做前后半程对比,已扣除联赛差异): 黄牌/场有一定个人稳定性(相关约 0.24~0.32);"
               "红牌、点球判罚、总进球基本没有个人稳定性(相关≈0)。75% 的裁判本赛季只有不到 5 场。所以不要仅凭某位裁判一个赛季的点球或红牌数据就说他\"爱判点球\"或\"爱出牌\";"
               "优先用【裁判档案】里 API-Football 统计的近 3 个赛季数据;没有档案才用联网查到的更大样本,并写明场次。\"偏向某队\"没有统计支持,必须给出具体场次和数据,没有就写\"没有证据\",不得暗示裁判受贿或操纵比赛。"
               "裁判风格对大小球和让球的影响没有回测支持,只能给方向和\"微弱\"强度,不能单独作为倾向的依据。\n"
               "基线与判断标准(本系统 30 个联赛本赛季 5091 场的整体水平): 黄牌 3.86/场、红牌 0.18/场、点球判罚 0.27/场(含罚丢)、总进球 2.95/场;不同联赛基线本身有差异,要写明和哪个联赛比。"
               "单个裁判的数据要和基线比,差距在 1.5 个标准误以内都算普通波动,不要写\"偏高/偏严/爱判点球\":样本 200 场时标准误约为点球 ±0.04、红牌 ±0.03、黄牌 ±0.14,"
               "样本 30 场时约为 ±0.10、±0.08、±0.36。例如一位执法 200 场的裁判点球 0.29/场,和基线 0.27 只差 0.02,不到半个标准误,属于普通水平,不能据此倾向大球。")


AUTHORITY = ("当值裁判以 API-Football 为准:联网查到的其他说法(赛前媒体、旧的指派、聚合站)与它不一致时,只用一句话提示差异并写明来源和时间,"
             "仍按 API-Football 的裁判继续分析,不要写\"裁判身份未定\"、也不要把两个人并列分析。")


def _timing(match_id: str, fetched_utc: datetime) -> str:
    """查询发生在开赛前还是开赛后: 开赛后查到的是实际执法的裁判, 比赛前的媒体报道更可靠。"""
    ko = _kickoff(match_id)
    if ko is None:
        return ""
    fetched_ts = fetched_utc.replace(tzinfo=timezone.utc).timestamp()
    return "开赛后查询,即实际执法的裁判" if fetched_ts >= ko else "赛前指派,临场可能更换"


def render(match_id: str, home: str, away: str) -> str:
    c = load_cached(match_id)
    if c is None:
        return ("\n【裁判】本场当值裁判还没有查询(或本场未对应到 API-Football)。需要用户说\"请关联本场裁判\"才会查询;"
                "没有数据时请联网搜索官方指派,查不到就明说,不要凭印象写裁判。\n" + RELIABILITY)
    at = c["fetchedAt"].replace(tzinfo=timezone.utc).astimezone(_BJ).strftime("%m-%d %H:%M")
    if not c["referee"]:
        return (f"\n【裁判】(来源 API-Football,查询于 {at} 北京时间)当值裁判尚未公布。联赛通常赛前 1~2 天公布,欧战更早;"
                "请联网查官方指派(如各联赛裁判委员会、UEFA 官网、赛前新闻),查到官方指派就按它分析并写明来源和时间;只有多个来源互相矛盾、或查不到时才写\"裁判未公布/未确定\"。\n" + RELIABILITY)
    tm = _timing(match_id, c["fetchedAt"])
    try:
        from .referee_profile import render as render_profile
        prof = render_profile(match_id, c["referee"], home, away)
    except Exception:  # noqa: BLE001  档案算不出来不影响裁判名字本身
        logger.exception("裁判档案渲染失败 %s", match_id)
        prof = ""
    ask = ("有【裁判档案】时以它为主,联网只补争议判罚、执法尺度和媒体评价;" if prof else "请联网查这位裁判的资料(多个来源交叉,中英文名都试一次),")
    return (f"\n【裁判】本场当值裁判: {c['referee']}(来源 API-Football,查询于 {at} 北京时间" + (f",{tm}" if tm else "") + ")。"
            f"{ask}再分析风格与倾向。\n" + AUTHORITY + "\n" + RELIABILITY + (("\n" + prof) if prof else ""))
