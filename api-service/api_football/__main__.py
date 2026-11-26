"""python -m api_football map [--apply]   对在售场次做映射(默认只预览不写库)
python -m api_football set-team 中文队名 AF球队id AF英文名   人工指定映射
python -m api_football init               只建表"""
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
    elif a[0] == "set-team" and len(a) == 4:
        schema.ensure_tables()
        mapping.set_team(a[1], int(a[2]), a[3])
        print("ok")
    else:
        print(__doc__)


main()
