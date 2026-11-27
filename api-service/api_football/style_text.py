"""把球队本赛季风格指标写成给聊天看的短文字: 首发对比(相对该队自己的基线)、教练、客场旅途。

原则: 只描述并给出"相对该队自己习惯"的参照, 不声称这些因素影响进球(没有回测); 样本不足(<5 场)明确标注。
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from . import team_style as ts

MIN_GAMES = 5
FAR_KM = 1500
FAR_TZ = 3.0


def lineup_compare_text(label: str, name: str, xi: List[Dict[str, Any]], formation: Optional[str], coach_name: Optional[str],
                        history: List[Dict[str, Any]], is_home: bool, coach_id: Optional[int] = None) -> str:
    """history: 本场之前该队的已完赛(旧→新)。返回 1~2 行文字, 没有历史返回空串。"""
    if not history:
        return ""
    xi_ids = [x["id"] for x in xi if x.get("id")]
    cmp = ts.compare_lineup(xi_ids, formation, history, is_home)
    st = ts.summarize(history, [], [])
    last = history[-1]
    n = len(history)
    parts = []
    if formation:
        ch = "(与上一场不同)" if cmp.get("formation_changed") else "(与上一场相同)"
        usual = f";该队{'主场' if is_home else '客场'}常用 {cmp['side_usual']}" if cmp.get("side_usual") else ""
        parts.append(f"本场阵型 {formation},上一场 {last.get('formation') or '未知'}{ch}{usual}")
    if cmp.get("vs_last_changes") is not None:
        k = cmp["vs_last_changes"]
        out_names = [last["names"].get(i) for i in last["xi"] if i not in set(xi_ids)]
        in_names = [x.get("name") for x in xi if x.get("id") and x["id"] not in set(last["xi"])]
        who = f"(换下 {'、'.join(filter(None, out_names[:4]))};换上 {'、'.join(filter(None, in_names[:4]))})" if k else ""
        if cmp.get("baseline_mean") is not None:
            if cmp.get("abnormal"):
                verdict = "明显多于该队自己的习惯"
            elif k > cmp["baseline_mean"]:
                verdict = "略多于习惯但在该队出现过的范围内" if k <= (cmp["baseline_max"] or 0) else "多于习惯"
            else:
                verdict = "不多于习惯"
            parts.append(f"首发较上一场换了 {k} 人{who},该队本季相邻两场平均换 {cmp['baseline_mean']} 人、最多 {cmp['baseline_max']} 人 → {verdict}")
        else:
            parts.append(f"首发较上一场换了 {k} 人{who}(历史场次太少,没有换人基线)")
    coach_bits = []
    if st["coach"]:
        last_id, cn = st["coach"]
        # 按教练 id 判断换帅: 接口不同时间返回的教练名写法不一致(全名/缩写), 按名字比较会误报; 本场没有 id 就不下结论
        if coach_id and last_id and coach_id != last_id:
            coach_bits.append(f"教练变更(上一场 {cn},本场 {coach_name or coach_id})")
        else:
            coach_bits.append(f"教练 {cn},任内已踢 {st['games_under_coach']} 场" + ("(本季换过帅)" if st["coach_changed"] else ""))
    nform = len(set(st["formations"]))
    coach_bits.append(f"本季使用过 {nform} 种阵型({'稳定' if nform <= 2 else '多变'})")
    parts.append(";".join(coach_bits))
    small = f"(样本仅 {n} 场,不稳)" if n < MIN_GAMES else f"(基于该队已入库的 {n} 场,含联赛与杯赛)"
    return f"{label}{name} 阵容对比{small}: " + "。".join(parts) + "。"


def travel_text(away_name: str, trip: Optional[Dict[str, Any]]) -> str:
    """只有明显较远(>=1500km 或时差>=3 小时)才输出; trip 来自 geo.travel。"""
    if not trip:
        return ""
    far = trip["km"] >= FAR_KM or (trip.get("tz_diff") is not None and abs(trip["tz_diff"]) >= FAR_TZ)
    if not far:
        return ""
    tz = f",时差 {trip['tz_diff']:+g} 小时" if trip.get("tz_diff") is not None and abs(trip["tz_diff"]) >= 1 else ""
    return (f"\n【客场旅途】客队{away_name}从{trip['from']}到{trip['to']}: 直线约 {trip['km']} 公里{tz}。"
            "说明: 球场没有经纬度,按城市地理编码估算,比赛球场缺失时用主队主场代替;旅途疲劳对进球和盘口的影响没有回测,只作提示,不是方向证据。")


def travel_note(match_id: str, away_name: str) -> str:
    """按 af_fixture_map 找到主客队, 算客队旅途。没有映射/坐标返回空串。"""
    try:
        from .injuries import _kickoff, _mapping
        from . import geo
        mp = _mapping(match_id)
        ko = _kickoff(match_id)
        if not mp or not ko:
            return ""
        when = datetime.fromtimestamp(ko, timezone.utc).replace(tzinfo=None)
        return travel_text(away_name, geo.travel(int(mp["af_away_id"]), None, when, int(mp["af_home_id"])))
    except Exception:  # noqa: BLE001  旅途算不出来不影响其余内容
        return ""
