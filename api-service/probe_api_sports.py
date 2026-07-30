#!/usr/bin/env python3
"""API-SPORTS (API-Football v3) 可行性探针。

用法:
  export API_SPORTS_KEY=xxx   # 或写入 api-service/.env
  cd api-service && python3 probe_api_sports.py

测试内容:
  1) 账号配额 /status
  2) 联赛 coverage（伤停/阵容/统计开关）
  3) 按日期搜 fixture（对齐竞彩在售日）
  4) lineups / injuries / players(进球) / standings.form
"""
from __future__ import annotations

import json
import os
import sys
from datetime import date, timedelta
from typing import Any, Dict, List, Optional

import httpx

try:
    from dotenv import load_dotenv
    load_dotenv(os.path.join(os.path.dirname(__file__), ".env"))
except Exception:
    pass

BASE = "https://v3.football.api-sports.io"
KEY = os.getenv("API_SPORTS_KEY") or os.getenv("APISPORTS_KEY") or ""


def client() -> httpx.Client:
    if not KEY:
        print("缺少 API_SPORTS_KEY。到 https://dashboard.api-sports.io/ 注册 Free 档，把 key 写入 api-service/.env")
        sys.exit(2)
    return httpx.Client(
        base_url=BASE,
        headers={"x-apisports-key": KEY},
        timeout=30.0,
    )


def get(c: httpx.Client, path: str, **params) -> Dict[str, Any]:
    r = c.get(path, params={k: v for k, v in params.items() if v is not None})
    data = r.json()
    errs = data.get("errors")
    if errs:
        # api-sports 有时 errors 是 {} 空对象
        if isinstance(errs, dict) and errs:
            raise RuntimeError(f"{path} errors={errs}")
        if isinstance(errs, list) and errs:
            raise RuntimeError(f"{path} errors={errs}")
    return data


def remaining(data: Dict[str, Any]) -> str:
    return (
        f"req={data.get('results')} "
        f"paging={data.get('paging')} "
        # headers often mirrored? not in body
    )


def section(title: str) -> None:
    print(f"\n===== {title} =====")


def main() -> None:
    with client() as c:
        # 1) status / account
        section("1) /status 账号与配额")
        st = get(c, "/status")
        acc = (st.get("response") or {})
        print(json.dumps(acc, ensure_ascii=False, indent=2)[:1200])
        # Also print rate limit headers from a lightweight call
        r = c.get("/timezone")
        print("headers:", {k: r.headers.get(k) for k in r.headers if "rate" in k.lower() or "request" in k.lower()})

        # 2) coverage for leagues we care about
        section("2) 重点联赛 coverage")
        # search by name fragments used in JCZQ
        league_queries = ["Premier League", "Champions League", "Super League", "Eliteserien", "Allsvenskan", "K League", "J1"]
        seen = set()
        for q in league_queries:
            data = get(c, "/leagues", search=q)
            for item in (data.get("response") or [])[:3]:
                league = item.get("league") or {}
                lid = league.get("id")
                if lid in seen:
                    continue
                seen.add(lid)
                seasons = item.get("seasons") or []
                cur = next((s for s in seasons if s.get("current")), seasons[-1] if seasons else None)
                cov = (cur or {}).get("coverage") or {}
                print(
                    f"L{lid} {league.get('name')} / {item.get('country',{}).get('name')} "
                    f"season={cur.get('year') if cur else None} "
                    f"lineups={cov.get('fixtures',{}).get('lineups')} "
                    f"injuries={cov.get('injuries')} "
                    f"stats={cov.get('fixtures',{}).get('statistics_fixtures')} "
                    f"players={cov.get('players')} "
                    f"standings={cov.get('standings')} "
                    f"odds={cov.get('odds')}"
                )

        # 3) fixtures around today (and JCZQ sample dates)
        section("3) 按日期拉 fixtures（今日±1）")
        days = [
            date.today().isoformat(),
            (date.today() + timedelta(days=1)).isoformat(),
            (date.today() - timedelta(days=1)).isoformat(),
        ]
        fixtures: List[Dict[str, Any]] = []
        for d in days:
            data = get(c, "/fixtures", date=d)
            resp = data.get("response") or []
            print(f"{d}: {len(resp)} fixtures (results={data.get('results')})")
            # keep UCL / interesting
            for fx in resp:
                league = (fx.get("league") or {}).get("name") or ""
                if any(k in league for k in ("Champions", "Europa", "Conference", "Premier", "Super League", "Eliteserien", "Allsvenskan")):
                    fixtures.append(fx)
        # dedupe by fixture id
        uniq = {}
        for fx in fixtures:
            uniq[(fx.get("fixture") or {}).get("id")] = fx
        fixtures = list(uniq.values())[:12]
        print(f"抽样关注场次: {len(fixtures)}")
        for fx in fixtures[:8]:
            fi = fx.get("fixture") or {}
            teams = fx.get("teams") or {}
            print(
                f"  fid={fi.get('id')} {fi.get('date')} "
                f"{(teams.get('home') or {}).get('name')} vs {(teams.get('away') or {}).get('name')} "
                f"| {(fx.get('league') or {}).get('name')} status={fi.get('status',{}).get('short')}"
            )

        # Try find Kairat / Omonia specifically (current JCZQ sample)
        section("3b) 队名搜索 Kairat / Omonia")
        for name in ("Kairat", "Omonia", "Almaty"):
            data = get(c, "/teams", search=name)
            for t in (data.get("response") or [])[:5]:
                team = t.get("team") or {}
                print(f"  team {team.get('id')} {team.get('name')} ({team.get('country')})")

        # fixtures for team if found
        kairat_id = None
        data = get(c, "/teams", search="Kairat")
        for t in data.get("response") or []:
            if "Kairat" in ((t.get("team") or {}).get("name") or ""):
                kairat_id = (t.get("team") or {}).get("id")
                break
        sample_fixture_id: Optional[int] = None
        if kairat_id:
            data = get(c, "/fixtures", team=kairat_id, next=5)
            for fx in data.get("response") or []:
                fi = fx.get("fixture") or {}
                teams = fx.get("teams") or {}
                print(
                    f"  next: fid={fi.get('id')} {fi.get('date')} "
                    f"{(teams.get('home') or {}).get('name')} vs {(teams.get('away') or {}).get('name')}"
                )
                sample_fixture_id = sample_fixture_id or fi.get("id")
                fixtures.insert(0, fx)

        if not sample_fixture_id and fixtures:
            sample_fixture_id = (fixtures[0].get("fixture") or {}).get("id")

        # 4) lineups / injuries for sample fixtures
        section("4) lineups / injuries 抽样")
        tested = 0
        for fx in fixtures:
            if tested >= 5:
                break
            fid = (fx.get("fixture") or {}).get("id")
            if not fid:
                continue
            teams = fx.get("teams") or {}
            label = f"{(teams.get('home') or {}).get('name')} vs {(teams.get('away') or {}).get('name')}"
            lu = get(c, "/fixtures/lineups", fixture=fid)
            inj = get(c, "/injuries", fixture=fid)
            lu_resp = lu.get("response") or []
            inj_resp = inj.get("response") or []
            print(f"\nfixture={fid} {label}")
            if not lu_resp:
                print("  lineups: EMPTY")
            for side in lu_resp:
                form = side.get("formation")
                start = side.get("startXI") or []
                subs = side.get("substitutes") or []
                coach = (side.get("coach") or {}).get("name")
                tname = (side.get("team") or {}).get("name")
                names = [((x.get("player") or {}).get("name")) for x in start[:11]]
                print(f"  lineup {tname}: formation={form} coach={coach} XI={len(start)} bench={len(subs)}")
                if names:
                    print(f"    start: {', '.join(n for n in names if n)}")
            print(f"  injuries: {len(inj_resp)}")
            for row in inj_resp[:6]:
                player = (row.get("player") or {}).get("name")
                reason = (row.get("player") or {}).get("reason")
                tname = (row.get("team") or {}).get("name")
                print(f"    - {tname}: {player} ({reason})")
            tested += 1

        # 5) player season goals for one lineup player if any
        section("5) /players 赛季进球（若有阵容）")
        player_id = None
        season = date.today().year
        if sample_fixture_id:
            lu = get(c, "/fixtures/lineups", fixture=sample_fixture_id)
            for side in lu.get("response") or []:
                for x in side.get("startXI") or []:
                    player_id = (x.get("player") or {}).get("id")
                    if player_id:
                        break
                if player_id:
                    break
        if player_id:
            data = get(c, "/players", id=player_id, season=season)
            resp = data.get("response") or []
            if not resp:
                data = get(c, "/players", id=player_id, season=season - 1)
                resp = data.get("response") or []
                season = season - 1
            if resp:
                p = resp[0]
                player = p.get("player") or {}
                print(f"player {player.get('id')} {player.get('name')} season={season}")
                for strow in p.get("statistics") or []:
                    team = (strow.get("team") or {}).get("name")
                    league = (strow.get("league") or {}).get("name")
                    goals = ((strow.get("goals") or {}).get("total"))
                    apps = ((strow.get("games") or {}).get("appearences"))
                    print(f"  {league} / {team}: apps={apps} goals={goals}")
            else:
                print("players: empty for sample id", player_id)
        else:
            print("无可用首发球员 id（线up 可能尚未公布）→ 跳过")

        # 6) standings form sample (EPL id=39)
        section("6) /standings form 抽样英超")
        data = get(c, "/standings", league=39, season=2025)
        resp = data.get("response") or []
        if resp:
            table = ((resp[0].get("league") or {}).get("standings") or [[]])[0]
            for row in table[:5]:
                print(
                    f"  #{row.get('rank')} {row.get('team',{}).get('name')} "
                    f"pts={row.get('points')} form={row.get('form')}"
                )
        else:
            # try 2024
            data = get(c, "/standings", league=39, season=2024)
            resp = data.get("response") or []
            print("2025 empty, 2024 results=", data.get("results"))
            if resp:
                table = ((resp[0].get("league") or {}).get("standings") or [[]])[0]
                for row in table[:5]:
                    print(
                        f"  #{row.get('rank')} {row.get('team',{}).get('name')} "
                        f"pts={row.get('points')} form={row.get('form')}"
                    )

        section("DONE")
        print("若 lineups/injuries 多为 EMPTY：正常（冷门/过早）；热门联赛临近开赛再测。")
        print("对照竞彩需另建 team/fixture 映射（队名英文化）。")


if __name__ == "__main__":
    main()
