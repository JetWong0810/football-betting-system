"""赛程密度: 休息天数、近 14 天场次、下一场的赛事与间隔, 用现有的近期战绩/未来赛程数据直接算, 不联网。

口径: 数据里只有日期没有开球时间, 所以天数按日历日估算, 精度约 ±1 天。
证据地位: 之前的回测里, 联赛场次的休息天数差对赢盘没有显著影响(t=-1.8), 所以本块只作为"首发轮换风险"的背景,
不是方向证据; 说明文字里写明, 避免模型把它当成加分项。
"""
from __future__ import annotations

from datetime import date, datetime
from typing import Any, Dict, List, Optional, Tuple

CUP_KEYS = ("欧冠", "欧联", "欧协联", "欧罗巴", "亚冠", "解放者", "杯", "超级杯", "联赛杯")
WINDOW_DAYS = 14


def _d(s: Any) -> Optional[date]:
    try:
        return datetime.strptime(str(s)[:10], "%Y-%m-%d").date()
    except (TypeError, ValueError):
        return None


def is_cup(comp: Optional[str]) -> bool:
    return any(k in (comp or "") for k in CUP_KEYS)


def team_schedule(kick: date, recent: List[Dict[str, Any]], future: List[Dict[str, Any]]) -> Dict[str, Any]:
    """recent: 开赛日之前的比赛(新→旧或任意顺序); future: 开赛日及以后。返回指标字典, 缺数据的字段为 None。"""
    past = sorted([(d, r) for r in recent or [] if (d := _d(r.get("date"))) and d < kick], key=lambda x: x[0], reverse=True)
    nxt = sorted([(d, r) for r in future or [] if (d := _d(r.get("date"))) and d > kick], key=lambda x: x[0])
    out: Dict[str, Any] = {"rest": None, "last_comp": None, "n14": None, "next_gap": None, "next_comp": None}
    if past:
        out["rest"] = (kick - past[0][0]).days
        out["last_comp"] = past[0][1].get("competition")
        out["n14"] = sum(1 for d, _ in past if (kick - d).days <= WINDOW_DAYS)
    if nxt:
        out["next_gap"] = (nxt[0][0] - kick).days
        out["next_comp"] = nxt[0][1].get("competition")
    return out


def _team_text(label: str, name: str, s: Dict[str, Any]) -> str:
    if s["rest"] is None and s["next_gap"] is None:
        return f"{label}{name}: 无赛程数据"
    parts = []
    if s["rest"] is not None:
        parts.append(f"距上一场约 {s['rest']} 天({s['last_comp'] or '赛事未知'}{',杯赛/欧战' if is_cup(s['last_comp']) else ''}),近 {WINDOW_DAYS} 天已踢 {s['n14']} 场")
    if s["next_gap"] is not None:
        flag = ",杯赛/欧战,可能影响本场轮换" if is_cup(s["next_comp"]) and s["next_gap"] <= 4 else ""
        parts.append(f"下一场约 {s['next_gap']} 天后({s['next_comp'] or '赛事未知'}{flag})")
    return f"{label}{name}: " + ";".join(parts)


def schedule_text(kick_date: str, home: str, away: str, home_recent, away_recent, home_future, away_future) -> str:
    kick = _d(kick_date)
    if kick is None:
        return ""
    sh = team_schedule(kick, home_recent, home_future)
    sa = team_schedule(kick, away_recent, away_future)
    if sh["rest"] is None and sa["rest"] is None and sh["next_gap"] is None and sa["next_gap"] is None:
        return ""
    lines = ["\n【赛程密度】(按日期估算天数,精度约 ±1 天)", _team_text("主队", home, sh), _team_text("客队", away, sa)]
    if sh["rest"] is not None and sa["rest"] is not None:
        d = sh["rest"] - sa["rest"]
        if d:
            lines.append(f"休息天数差: {home if d > 0 else away}多休息 {abs(d)} 天")
    lines.append("说明: 本系统回测里联赛场次的休息天数差对赢盘没有显著影响(t=-1.8),这里只作为首发轮换风险的背景,不是方向证据;"
                 "只有一方休息明显更少、或下一场是临近的欧战/杯赛时,才值得结合官方首发看有没有轮换。")
    return "\n".join(lines)
