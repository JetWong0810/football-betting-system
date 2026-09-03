import logging
import os
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional

import httpx

import settings
from repository import OddsRepository
from scraper.score_sporttery import clear_cache as clear_score_cache, fetch_ft_scores

logger = logging.getLogger(__name__)

EURO_TTL_SEC = int(os.getenv("ZGZCW_EURO_TTL_SEC", "2700"))
FORM_TTL_SEC = int(os.getenv("ZGZCW_FORM_TTL_SEC", "21600"))
OU_TTL_SEC = int(os.getenv("ZGZCW_OU_TTL_SEC", "2700"))
TICKS_TTL_SEC = int(os.getenv("ZGZCW_TICKS_TTL_SEC", "2700"))

# 体彩 matchDate/matchTime 是北京墙钟；容器常为 UTC，naive .timestamp() 会 +8h
_BJ = timezone(timedelta(hours=8))


def _normalize_wall_clock(match_date, match_time) -> Optional[tuple]:
    """归一化 DB/API 的日期时间 → (YYYY-MM-DD, HH:MM:SS)。"""
    if match_date is None or match_time is None or match_time == "":
        return None
    if hasattr(match_date, "strftime"):
        d = match_date.strftime("%Y-%m-%d")
    else:
        d = str(match_date)[:10]
    if isinstance(match_time, timedelta):
        total = int(match_time.total_seconds())
        if total < 0:
            return None
        h, rem = divmod(total, 3600)
        m, s = divmod(rem, 60)
        t = f"{h:02d}:{m:02d}:{s:02d}"
    else:
        t = str(match_time).strip()
        if len(t) == 5 and t[2] == ":":
            t = t + ":00"
    return d, t


def beijing_kickoff_ts(match_date, match_time) -> Optional[int]:
    """把竞彩开赛墙钟(北京)转成 unix 秒。"""
    norm = _normalize_wall_clock(match_date, match_time)
    if not norm:
        return None
    d, t = norm
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M"):
        try:
            return int(datetime.strptime(f"{d} {t}", fmt).replace(tzinfo=_BJ).timestamp())
        except ValueError:
            continue
    return None


def derive_sale_date(match: Dict) -> Optional[str]:
    """从 match_number(YYMMDD) 推导售卖日期；兜底用 match_date"""
    mn = str(match.get("match_number") or "").strip()
    if len(mn) >= 6 and mn[:6].isdigit():
        yy, mm, dd = mn[:2], mn[2:4], mn[4:6]
        # 校验合法日期
        try:
            datetime.strptime(f"20{yy}-{mm}-{dd}", "%Y-%m-%d")
            return f"20{yy}-{mm}-{dd}"
        except ValueError:
            pass
    return match.get("match_date")


def _asian_close_unchanged(match: Dict, line: Dict) -> bool:
    """库内终盘与新抓水位都在 0.005 内则跳过写入。"""
    try:
        old_hc = match.get("asian_handicap")
        old_h = match.get("asian_home_odds")
        if old_hc is None or old_h is None or line.get("close_home") is None:
            return False
        if abs(float(old_hc) - float(line["close_hc"])) > 0.005:
            return False
        if abs(float(old_h) - float(line["close_home"])) > 0.005:
            return False
        old_a = match.get("asian_away_odds")
        new_a = line.get("close_away")
        if old_a is not None and new_a is not None:
            if abs(float(old_a) - float(new_a)) > 0.005:
                return False
        return True
    except (TypeError, ValueError):
        return False


def _is_stale(ts, ttl_sec: int) -> bool:
    if ts is None:
        return True
    if isinstance(ts, str):
        raw = ts.replace("Z", "")
        try:
            ts = datetime.fromisoformat(raw)
        except ValueError:
            return True
    if getattr(ts, "tzinfo", None):
        ts = ts.replace(tzinfo=None)
    try:
        return (datetime.now() - ts).total_seconds() > ttl_sec
    except TypeError:
        return True


def parse_decimal(value: Optional[str]) -> Optional[float]:
    if value in (None, "", "-", "null"):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def parse_single_flag(value: Optional[object]) -> int:
    if value is None:
        return 0
    if isinstance(value, bool):
        return 1 if value else 0
    if isinstance(value, (int, float)):
        return 1 if int(value) == 1 else 0
    if isinstance(value, str):
        token = value.strip().lower()
        return 1 if token in {"1", "true", "y", "yes"} else 0
    return 0


def extract_pool_single_flags(match_data: Dict) -> Dict[str, int]:
    flags: Dict[str, int] = {}
    for pool in match_data.get("poolList", []):
        code = str(pool.get("poolCode") or "").strip().lower()
        if not code:
            continue
        flag = pool.get("single")
        if flag is None:
            flag = pool.get("bettingSingle")
        flags[code] = parse_single_flag(flag)
    return flags


class SportterySyncService:
    def __init__(self, repository: Optional[OddsRepository] = None):
        self.repository = repository or OddsRepository()
        self.client = httpx.Client(timeout=settings.HTTP_TIMEOUT, headers={"User-Agent": settings.USER_AGENT})
        self.stats = {"matches": 0, "odds": 0}

    def fetch_pool(self, pool_code: str) -> Dict:
        url = f"{settings.SPORTTERY_API_URL}?channel=c&poolCode={pool_code}"
        response = self.client.get(url)
        response.raise_for_status()
        return response.json()

    RESULT_API_URL = (
        "https://webapi.sporttery.cn/gateway/uniform/football/"
        "getUniformMatchResultV1.qry"
    )

    def run_once(self) -> Dict[str, int]:
        self.stats = {"matches": 0, "odds": 0, "scores": 0, "closing_odds": 0, "asian": 0}
        for pool_name, pool_code in settings.POOL_CODES.items():
            data = self.fetch_pool(pool_code)
            self.parse_pool(pool_name, data)
        # 回填已完赛但缺比分的比赛(最近3天，体彩赛果 sectionsNo999)
        try:
            self.stats["scores"] = self.backfill_scores(days=3)
        except Exception as e:
            logger.warning(f"比分回填失败: {e}")
        # 赛果终赔校正(在售池封盘前停更, history 末条常不是真终盘)
        try:
            self.stats["closing_odds"] = self.backfill_closing_odds(days=3)
        except Exception as e:
            logger.warning(f"终盘回填失败: {e}")
        # 在售 Bet365 亚盘定时刷新(终盘覆盖, 供同赔页)
        try:
            self.stats["asian"] = self.refresh_live_asian_bet365()
        except Exception as e:
            logger.warning(f"在售亚盘刷新失败: {e}")
        self.repository.finalize_sync(self.stats["matches"], self.stats["odds"])
        return self.stats

    def fetch_match_results(self, begin_date: str, end_date: str) -> List[Dict]:
        """体彩赛果列表。h/d/a = 胜平负终赔。"""
        params = {
            "matchBeginDate": begin_date,
            "matchEndDate": end_date,
            "leagueId": "",
            "pageSize": 100,
            "pageNo": 1,
            "isFix": 0,
            "matchPage": 1,
            "pcOrWap": 1,
        }
        rows: List[Dict] = []
        while True:
            resp = self.client.get(self.RESULT_API_URL, params=params)
            resp.raise_for_status()
            data = resp.json()
            if not data.get("success"):
                break
            batch = (data.get("value") or {}).get("matchResult") or []
            if not batch:
                break
            rows.extend(batch)
            total = int((data.get("value") or {}).get("total") or 0)
            if len(rows) >= total or len(batch) < params["pageSize"]:
                break
            params["pageNo"] += 1
        return rows

    def backfill_closing_odds(self, days: int = 3) -> int:
        """从体彩赛果 API 回填 spf 终盘。

        在售计算器接口在封盘/停售后不再推送变动, scraper 末条常停在中间值
        (例:索尔纳 1.37, 真终盘 1.40)。赛果页 h/d/a 为官方终赔。
        """
        end = datetime.now(_BJ).date()
        begin = end - timedelta(days=max(days - 1, 0))
        begin_s, end_s = begin.isoformat(), end.isoformat()
        try:
            results = self.fetch_match_results(begin_s, end_s)
        except Exception as e:
            logger.warning(f"拉取赛果终赔失败 {begin_s}~{end_s}: {e}")
            return 0
        if not results:
            return 0

        updated = 0
        for m in results:
            mid = str(m.get("matchId") or "").strip()
            h, d, a = m.get("h"), m.get("d"), m.get("a")
            if not mid or h in (None, "", "-") or d in (None, "", "-") or a in (None, "", "-"):
                continue
            try:
                win, draw, lose = float(h), float(d), float(a)
            except (TypeError, ValueError):
                continue
            # change_time 用开赛 UTC(与 append_odds_history 的 utcnow 口径一致)
            ct = None
            kickoff_ts = self.repository.get_match_timestamp(mid)
            if kickoff_ts:
                ct = datetime.utcfromtimestamp(int(kickoff_ts)).replace(microsecond=0)
            if self.repository.apply_closing_spf(mid, win, draw, lose, change_time=ct):
                updated += 1
                logger.info(
                    f"  终盘 {m.get('homeTeam')} {win:.2f}/{draw:.2f}/{lose:.2f} {m.get('awayTeam')}"
                )
        if updated:
            logger.info(f"终盘回填: {updated} 场 ({begin_s}~{end_s})")
        return updated

    def backfill_scores(self, days: int = 3) -> int:
        """回填已开赛但缺比分的比赛(数据源: 体彩赛果 API)。

        开赛满 2h 的优先抓(大概率已完赛可出分)；有分才写 finished，不按时长盲标。
        """
        pending = self.repository.get_finished_without_score(days=days)
        if not pending:
            return 0

        now_ts = int(datetime.now().timestamp())
        ripe = sum(
            1 for m in pending
            if (m.get("match_timestamp") or 0) <= now_ts - 2 * 3600
        )
        logger.info(f"待回填比分: {len(pending)} 场(其中开赛≥2h优先 {ripe} 场)")
        dates = [str(m.get("match_date") or "")[:10] for m in pending if m.get("match_date")]
        end = datetime.now(_BJ).date()
        begin = end - timedelta(days=max(days, 1))
        begin_s = min(dates + [begin.isoformat()])
        end_s = max(dates + [end.isoformat()])
        clear_score_cache()
        try:
            scores = fetch_ft_scores(begin_s, end_s)
        except Exception as e:
            logger.warning(f"拉取体彩赛果比分失败 {begin_s}~{end_s}: {e}")
            return 0
        updated = 0
        for m in pending:
            score = scores.get(str(m.get("match_id") or "").strip())
            if not score:
                continue
            self.repository.update_match_score(m["match_id"], score[0], score[1])
            logger.info(f"  回填 {m.get('home_team_name')} {score[0]}:{score[1]} {m.get('away_team_name')}")
            updated += 1
        return updated

    def refresh_live_asian_bet365(self, max_workers: int = 4, overwrite_open: bool = False) -> int:
        """在售场刷新亚盘/欧赔/基本面/指数。ypdb 优先, 剩余预算才开 bjop/bsls/dxdb/zhishu。

        Bet365 写入 jczq_ah_history; 主流公司 JSON 写入 jczq_fenxi_cache;
        Bet365 亚盘 ticks 写入 jczq_ah_ticks, 不覆盖 history 终盘。
        Playwright 串行, 二次验证中止本轮。max_workers 保留签名, 足彩网路径忽略。
        """
        from scraper.zgzcw_fenxi import FenxiSession
        from scraper.zgzcw_live import fetch_jczq_live_map

        live = self.repository.list_live_for_asian()
        if not live:
            return 0
        logger.info(f"在售亚盘刷新: {len(live)} 场")

        code_map = fetch_jczq_live_map()
        for m in live:
            info = code_map.get(m.get("match_code") or "")
            if not info or not info.get("fid"):
                continue
            try:
                self.repository.save_fid_zgzcw(
                    m["match_id"],
                    info["fid"],
                    home_rank=info.get("home_rank"),
                    away_rank=info.get("away_rank"),
                )
            except Exception as e:
                logger.warning(f"写 fid_zgzcw 失败 {m.get('match_id')}: {e}")
                continue
            m["fid_zgzcw"] = info["fid"]

        targets = [m for m in live if m.get("fid_zgzcw")]
        if not targets:
            logger.warning("zgzcw 未映射到在售场, 本轮亚盘跳过")
            return 0

        meta = self.repository.list_fenxi_meta([m["match_id"] for m in targets])
        updated = 0
        with FenxiSession() as sess:
            packs = {}
            for m in targets:
                if sess.aborted:
                    break
                mid = m.get("match_id")
                fid = m.get("fid_zgzcw")
                pack = sess.fetch_ypdb(fid)
                if not pack:
                    continue
                packs[mid] = pack
                companies = pack.get("companies") or []
                if companies:
                    try:
                        self.repository.upsert_fenxi_cache(mid, asian=companies)
                    except Exception as e:
                        logger.warning(f"亚盘缓存失败 {mid}: {e}")
                line = pack.get("bet365")
                if not line or line.get("close_hc") is None:
                    continue
                if not overwrite_open and _asian_close_unchanged(m, line):
                    sess.skipped += 1
                    continue
                try:
                    self.repository.upsert_asian_bet365(
                        mid,
                        fid=None,
                        raw_close_hc=float(line["close_hc"]),
                        raw_open_hc=line.get("open_hc"),
                        close_home=line.get("close_home"),
                        close_away=line.get("close_away"),
                        open_home=line.get("open_home"),
                        open_away=line.get("open_away"),
                        fid_zgzcw=str(fid),
                        overwrite_open=overwrite_open,
                    )
                except Exception as e:
                    logger.warning(f"亚盘落库失败 {mid}: {e}")
                    continue
                updated += 1
                logger.info(
                    f"  亚盘 {m.get('match_code')} cid={line.get('cid')} "
                    f"{line.get('open_hc')}→{line.get('close_hc')} {line.get('name')}"
                )

            for m in targets:
                if sess.aborted:
                    break
                mid = m.get("match_id")
                fid = m.get("fid_zgzcw")
                row_meta = meta.get(mid) or {}
                asian_changed = mid in packs and not _asian_close_unchanged(
                    m, (packs[mid].get("bet365") or {})
                )
                need_bjop = asian_changed or _is_stale(row_meta.get("euro_fetched_at"), EURO_TTL_SEC)
                need_bsls = _is_stale(row_meta.get("form_fetched_at"), FORM_TTL_SEC)
                if need_bjop and sess.remaining > 0:
                    euro = sess.fetch_bjop(fid)
                    if euro and euro.get("companies"):
                        try:
                            self.repository.upsert_fenxi_cache(mid, euro=euro)
                            logger.info(f"  欧赔 {m.get('match_code')} {len(euro['companies'])}家")
                        except Exception as e:
                            logger.warning(f"欧赔缓存失败 {mid}: {e}")
                if need_bsls and sess.remaining > 0:
                    form = sess.fetch_bsls(fid)
                    if form and (form.get("homeRecent") or form.get("awayRecent")):
                        try:
                            self.repository.upsert_fenxi_cache(mid, form=form)
                            logger.info(
                                f"  基本面 {m.get('match_code')} "
                                f"近{len(form.get('homeRecent') or [])}/"
                                f"{len(form.get('awayRecent') or [])} 交锋{len(form.get('h2h') or [])}"
                            )
                        except Exception as e:
                            logger.warning(f"基本面缓存失败 {mid}: {e}")

            for m in targets:
                if sess.aborted:
                    break
                mid = m.get("match_id")
                fid = m.get("fid_zgzcw")
                row_meta = meta.get(mid) or {}
                asian_changed = mid in packs and not _asian_close_unchanged(
                    m, (packs[mid].get("bet365") or {})
                )
                need_ou = asian_changed or _is_stale(row_meta.get("ou_fetched_at"), OU_TTL_SEC)
                need_ticks = asian_changed or _is_stale(
                    row_meta.get("ticks_fetched_at"), TICKS_TTL_SEC
                )
                if need_ou and sess.remaining > 0:
                    ou = sess.fetch_dxdb(fid)
                    if ou and ou.get("companies"):
                        try:
                            self.repository.upsert_fenxi_cache(mid, ou=ou)
                            logger.info(f"  大小球 {m.get('match_code')} {len(ou['companies'])}家")
                        except Exception as e:
                            logger.warning(f"大小球缓存失败 {mid}: {e}")
                if need_ticks and sess.remaining > 0:
                    ticks = sess.fetch_ypdb_zhishu(fid)
                    if ticks:
                        try:
                            n = self.repository.replace_ah_ticks(mid, ticks)
                            logger.info(f"  亚盘轴 {m.get('match_code')} {n}点")
                        except Exception as e:
                            logger.warning(f"亚盘轴落库失败 {mid}: {e}")
        logger.info(f"在售亚盘刷新完成: {updated}/{len(targets)} (列表{len(live)})")
        return updated

    # Parsing helpers -----------------------------------------------------
    def parse_pool(self, pool_name: str, data: Dict) -> None:
        if not data.get("success") or data.get("emptyFlag"):
            return
        match_info_list = data.get("value", {}).get("matchInfoList", [])
        for date_group in match_info_list:
            for match_data in date_group.get("subMatchList", []):
                if pool_name == "had_hhad":
                    single_flags = extract_pool_single_flags(match_data)
                    match = self.build_match(match_data, single_flags)
                    self.repository.upsert_match(match)
                    self.stats["matches"] += 1
                    for odds in self.build_had_hhad(match_data, single_flags):
                        self.repository.upsert_odds_wdl(odds)
                        self.repository.append_odds_history(odds)
                        self.stats["odds"] += 1
                elif pool_name == "crs":
                    items = self.build_crs(match_data)
                    self.repository.upsert_odds_score_bulk(str(match_data.get("matchId")), items)
                    self.stats["odds"] += len(items)
                elif pool_name == "ttg":
                    items = self.build_ttg(match_data)
                    self.repository.upsert_odds_goals_bulk(str(match_data.get("matchId")), items)
                    self.stats["odds"] += len(items)
                elif pool_name == "hafu":
                    items = self.build_hafu(match_data)
                    self.repository.upsert_odds_hafu_bulk(str(match_data.get("matchId")), items)
                    self.stats["odds"] += len(items)

    def build_match(self, match_data: Dict, single_flags: Optional[Dict[str, int]] = None) -> Dict:
        match_id = str(match_data.get("matchId"))
        match_date = match_data.get("matchDate")
        match_time = match_data.get("matchTime")
        timestamp = (
            beijing_kickoff_ts(match_date, match_time)
            if match_date and match_time
            else None
        )
        status_map = {
            "Selling": "not_started",
            "Finished": "finished",
            "Cancelled": "cancelled",
        }
        match_status = status_map.get(match_data.get("matchStatus"), "not_started")
        # 胜平负单固: 顶层 bettingSingle 偶发为0但 poolList.HAD.single=1, OR 写入 matches
        top_single = parse_single_flag(match_data.get("bettingSingle"))
        had_single = int((single_flags or {}).get("had") or 0)
        return {
            "match_id": match_id,
            "match_number": match_data.get("matchNumDate"),
            "match_code": match_data.get("matchNumStr"),
            "project_type": "football",
            "league_id": match_data.get("leagueId"),
            "league_name": match_data.get("leagueAbbName"),
            "league_full_name": match_data.get("leagueAllName"),
            "match_date": match_date,
            "match_time": match_time,
            "match_timestamp": timestamp,
            "home_team_id": match_data.get("homeTeamId"),
            "home_team_name": match_data.get("homeTeamAbbName"),
            "home_team_rank": match_data.get("homeRank"),
            "away_team_id": match_data.get("awayTeamId"),
            "away_team_name": match_data.get("awayTeamAbbName"),
            "away_team_rank": match_data.get("awayRank"),
            "is_single": 1 if (top_single or had_single) else 0,
            "match_status": match_status,
            "notice": match_data.get("matchTips"),
            "odds_update_time": match_data.get("oddsUpdateTime"),
        }

    def build_had_hhad(self, match_data: Dict, single_flags: Optional[Dict[str, int]] = None) -> List[Dict]:
        match_id = str(match_data.get("matchId"))
        results: List[Dict] = []
        single_flags = single_flags or {}
        default_single = parse_single_flag(match_data.get("bettingSingle"))

        had_data = match_data.get("had", {})
        if had_data and had_data.get("h"):
            is_single = single_flags.get("had", default_single)
            results.append(
                {
                    "match_id": match_id,
                    "odds_type": "had",
                    "handicap": 0,
                    "win_odds": parse_decimal(had_data.get("h")),
                    "draw_odds": parse_decimal(had_data.get("d")),
                    "lose_odds": parse_decimal(had_data.get("a")),
                    "win_support": parse_decimal(had_data.get("h_trend")),
                    "draw_support": parse_decimal(had_data.get("d_trend")),
                    "lose_support": parse_decimal(had_data.get("a_trend")),
                    "is_single": is_single,
                }
            )
        hhad_data = match_data.get("hhad", {})
        if hhad_data and hhad_data.get("h"):
            goal_line = hhad_data.get("goalLineValue", "0")
            try:
                handicap = float(goal_line)
            except (TypeError, ValueError):
                handicap = 0
            is_single = single_flags.get("hhad", default_single)
            results.append(
                {
                    "match_id": match_id,
                    "odds_type": "hhad",
                    "handicap": handicap,
                    "win_odds": parse_decimal(hhad_data.get("h")),
                    "draw_odds": parse_decimal(hhad_data.get("d")),
                    "lose_odds": parse_decimal(hhad_data.get("a")),
                    "win_support": parse_decimal(hhad_data.get("h_trend")),
                    "draw_support": parse_decimal(hhad_data.get("d_trend")),
                    "lose_support": parse_decimal(hhad_data.get("a_trend")),
                    "is_single": is_single,
                }
            )
        return results

    def build_crs(self, match_data: Dict) -> List[Dict]:
        match_id = str(match_data.get("matchId"))
        crs_data = match_data.get("crs", {})
        if not crs_data:
            return []
        items: List[Dict] = []
        segments = {
            "win": [
                ("1:0", "s01s00"), ("2:0", "s02s00"), ("2:1", "s02s01"),
                ("3:0", "s03s00"), ("3:1", "s03s01"), ("3:2", "s03s02"),
                ("4:0", "s04s00"), ("4:1", "s04s01"), ("4:2", "s04s02"),
                ("5:0", "s05s00"), ("5:1", "s05s01"), ("5:2", "s05s02"),
            ],
            "draw": [
                ("0:0", "s00s00"), ("1:1", "s01s01"), ("2:2", "s02s02"),
                ("3:3", "s03s03"),
            ],
            "lose": [
                ("0:1", "s00s01"), ("0:2", "s00s02"), ("1:2", "s01s02"),
                ("0:3", "s00s03"), ("1:3", "s01s03"), ("2:3", "s02s03"),
                ("0:4", "s00s04"), ("1:4", "s01s04"), ("2:4", "s02s04"),
                ("0:5", "s00s05"), ("1:5", "s01s05"), ("2:5", "s02s05"),
            ],
        }
        for result_type, pairs in segments.items():
            for label, key in pairs:
                odds_value = crs_data.get(key)
                if odds_value:
                    home, away = label.split(":")
                    items.append(
                        {
                            "result_type": result_type,
                            "home_score": int(home),
                            "away_score": int(away),
                            "score_label": label,
                            "odds": parse_decimal(odds_value),
                            "is_other": 0,
                        }
                    )
        special_map = {
            "win": ("s1sh", "胜其他"),
            "draw": ("spsh", "平其他"),
            "lose": ("sash", "负其他"),
        }
        for result_type, (key, label) in special_map.items():
            odds_value = crs_data.get(key)
            if odds_value:
                items.append(
                    {
                        "result_type": result_type,
                        # 用 -1 表示“其他”比分，避免插入 NULL 时唯一索引失效
                        "home_score": -1,
                        "away_score": -1,
                        "score_label": label,
                        "odds": parse_decimal(odds_value),
                        "is_other": 1,
                    }
                )
        return items

    def build_ttg(self, match_data: Dict) -> List[Dict]:
        ttg_data = match_data.get("ttg", {})
        if not ttg_data:
            return []
        ranges = [
            ("0", 0, 0, "s0"),
            ("1", 1, 1, "s1"),
            ("2", 2, 2, "s2"),
            ("3", 3, 3, "s3"),
            ("4", 4, 4, "s4"),
            ("5", 5, 5, "s5"),
            ("6", 6, 6, "s6"),
            ("7+", 7, None, "s7"),
        ]
        items = []
        for label, min_goals, max_goals, key in ranges:
            odds_value = ttg_data.get(key)
            if odds_value:
                items.append(
                    {
                        "goal_range": label,
                        "min_goals": min_goals,
                        "max_goals": max_goals,
                        "odds": parse_decimal(odds_value),
                    }
                )
        return items

    def build_hafu(self, match_data: Dict) -> List[Dict]:
        hafu_data = match_data.get("hafu", {})
        if not hafu_data:
            return []
        mapping = {
            "hh": ("win", "win", "胜胜"),
            "hd": ("win", "draw", "胜平"),
            "ha": ("win", "lose", "胜负"),
            "dh": ("draw", "win", "平胜"),
            "dd": ("draw", "draw", "平平"),
            "da": ("draw", "lose", "平负"),
            "ah": ("lose", "win", "负胜"),
            "ad": ("lose", "draw", "负平"),
            "aa": ("lose", "lose", "负负"),
        }
        items = []
        for key, (half, full, label) in mapping.items():
            odds_value = hafu_data.get(key)
            if odds_value:
                items.append(
                    {
                        "half_result": half,
                        "full_result": full,
                        "result_label": label,
                        "odds": parse_decimal(odds_value),
                    }
                )
        return items

    def close(self) -> None:
        self.client.close()
