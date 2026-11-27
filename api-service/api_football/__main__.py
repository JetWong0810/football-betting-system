"""python -m api_football map [--apply]   对在售场次做映射(默认只预览不写库)
python -m api_football set-team 中文队名 AF球队id AF英文名   人工指定映射
python -m api_football init               只建表
python -m api_football hist league <联赛id> [--apply]   本赛季比赛库(首发/事件/统计), 默认只统计不写库
python -m api_football hist teams <联赛id>              球队与球场
python -m api_football geocode                          给球场城市补经纬度/时区
python -m api_football style <球队id> <联赛id>          查看球队本赛季风格指标"""
import sys

from dotenv import load_dotenv

load_dotenv()
from . import mapping, schema  # noqa: E402


def main() -> None:
    a = sys.argv[1:]
    if not a or a[0] == "init":
        schema.ensure_tables()
        print("tables ok")
    elif a[0] == "map":
        apply = "--apply" in a
        if apply:
            schema.ensure_tables()
        r = mapping.run(apply=apply)
        print(f"待映射 {r['todo']} 场, 对上 {len(r['matched'])}, 未解决 {len(r['unresolved'])}, 请求 {r.get('requests')}, 今日剩余 {r.get('day_remaining')}"
              + ("" if apply else "  [预览, 未写库]"))
        for x in r["matched"]:
            print("  OK ", *x)
        for x in r["unresolved"]:
            print("  ?? ", *x, "(开赛时间前后候选数)")
    elif a[0] == "hist" and len(a) >= 3:
        from . import hist
        from .client import AfClient
        schema.ensure_tables()
        with AfClient() as c:
            if a[1] == "league":
                print(hist.sync_league(c, int(a[2]), apply="--apply" in a), "请求", c.requests, "今日剩余", c.day_remaining)
            elif a[1] == "teams":
                season = hist.current_season(c, int(a[2]))
                print("球队", hist.sync_teams(c, int(a[2]), season), "season", season)
    elif a[0] == "geocode":
        from . import geo
        print("已处理球场", geo.geocode_pending())
    elif a[0] == "style" and len(a) == 3:
        from . import hist, team_style
        from .client import AfClient
        with AfClient() as c:
            season = hist.current_season(c, int(a[2]))
        print(team_style.team_style(int(a[1]), int(a[2]), season))
    elif a[0] == "set-team" and len(a) == 4:
        schema.ensure_tables()
        mapping.set_team(a[1], int(a[2]), a[3])
        print("ok")
    else:
        print(__doc__)


main()
