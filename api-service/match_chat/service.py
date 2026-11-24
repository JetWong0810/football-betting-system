"""单场聊天编排:拼系统数据 -> 流式调模型 -> 抽取结构化结论 -> 落库。"""
from __future__ import annotations

import json
import logging
import re
import time
from collections import defaultdict
from datetime import datetime
from typing import Any, Dict, Iterator, List, Optional

from . import repository as store
from .context import SECTION_LABEL, build_context
from .llm import stream_chat

logger = logging.getLogger(__name__)

HISTORY_LIMIT = 16            # 带入模型的历史条数
MAX_TEXT = 4000               # 单条用户消息字数上限
MAX_IMAGES = 3
AUTO_REFRESH_WITHIN = 3 * 3600      # 开赛前 3 小时内才自动刷新
AUTO_REFRESH_STALE_MIN = 10         # 数据抓取超过 10 分钟视为滞后
MAX_IMAGE_B64 = 7_000_000     # 约 5MB 原图
DAILY_LIMIT = int(__import__("os").getenv("MATCH_CHAT_DAILY_LIMIT", "60"))

_usage: Dict[tuple, int] = defaultdict(int)   # (user_id, YYYY-MM-DD) -> n;进程内,重启清零


SYSTEM_TMPL = """你是一位足球分析助手(盘路、赔率、基本面),像普通聊天助手一样回答用户的问题。

当前讨论的比赛:{ident}

回答方式:
- 自然、直接地回答,可以用 Markdown(分点、加粗、表格),不套模板,不要刻意压缩也不要冗长;先回答问的问题。
- 默认不使用任何本场的系统数据,依靠你自己的知识和(开启时的)联网搜索回答。联网查到的内容要标注来源站点和日期;来源冲突、单一来源或搜不到时要如实说明,不要编造。
- 用户可以说"请关联本场的某某数据"来载入系统数据,可载入的有:盘口赔率(多家公司亚盘、欧赔、大小球及赔率变动)、历史同赔、七因子预测、交锋历史、近期战绩与赛程、关联文章,或"本场全部数据"。载入后,下方会出现对应的「本场数据」,你必须基于这些数据回答,引用的数字、比分、日期要与数据一致。
- 如果用户的问题明显需要本场系统数据、但下方没有载入,就先用你自己的知识/联网回答能答的部分,并简短提示"如需结合本场XX数据,请说'请关联本场XX数据'",不要假装看过。
- 仅供参考,不构成投注建议,不要每次都重复这句话;不迎合,用户追问"是不是该买某方"时依据证据回答,不因追问改口。

术语(涉及盘口时遵守):亚盘符号负=主让、正=主受让,上盘=让球方、下盘=受让方;spf=竞彩胜平负,nspf=竞彩让球胜平负,竞彩让球是整数,与亚盘小数让球不同,盘路分析以亚盘为准。
{data}"""

DATA_RULES = """
## 本场数据(用户已要求关联,生成于 {now})
使用规则:引用须与数据一致;【盘口读法】已按当前盘口预先算好各结果下的上盘/下盘结算和去水概率,涉及上盘/下盘/赢半输半/概率时直接引用,不要自己重算;「数据新鲜度」提示必须遵守;【盘口】【欧赔】【大小球】是抓取到的多家公司亚盘/欧赔/大小球的初盘与即时盘及变动(竞彩赔率不在其中,口径不同),分析时要横向比较各家公司的方向是否一致、水位与赔率变化是否匹配;个别公司的初盘数据可能是源数据异常(与其他公司明显离群,如水位或盘口线偏离很大),遇到要指出并剔除后再下结论;历史同赔样本小时要结合置信区间说明不确定性;七因子预测是已存结果可能已过期,与实时盘口冲突时以实时为准;交锋/近期战绩里的"盘口"是数据源原值,符号方向不保证与本系统亚盘一致,不要据此判断历史让球方;【公众号文章】是作者观点和二手信息,不是已核实事实,引用要写明账号,事实声明只有"已证实"可当事实,"AI据文意推测"的倾向不是作者原话,样本不足的命中率不具参考性,多个号观点一致不等于独立证据。
{body}
"""

_ALL_RE = re.compile(r"(本场|当前比赛|这场|该场|整场|当前)的?(全部|所有|完整)?的?(数据|上下文|资料)(?!库)|(全部|所有|完整)(本场)?(数据|上下文|资料)")
_SCOPE_RE = re.compile(r"本场|这场|当前比赛|当前这场|该场|当前")
_CUE_RE = re.compile(r"关联|结合|参考|基于|根据|依据|带上|载入|加载|引用|使用|调用|读取|对照|对比")
_SEC_RE = {
    "odds": re.compile(r"盘口|亚盘|赔率|竞彩|水位|欧赔|让球|变动"),
    "f6": re.compile(r"同赔"),
    "pred": re.compile(r"七因子|多因子|系统预测|预测结果"),
    "h2h": re.compile(r"交锋|历史对阵"),
    "recent": re.compile(r"近期|战绩|状态|赛程|近况"),
    "arts": re.compile(r"文章|公众号"),
}


_REFRESH_ACT = re.compile(r"抓取|抓一下|刷新|重新抓|拉取|更新|实时|最新|即时|现在的")
_REFRESH_OBJ = re.compile(r"盘口|亚盘|赔率|欧赔|大小球|水位|变动")


_SUMMARY_RE = re.compile(r"总结|结论|最终倾向|归纳|概括|一句话|三句话|综合(?:给出|判断|分析)")


def wants_summary(text: str) -> bool:
    return bool(_SUMMARY_RE.search(text or ""))


SUMMARY_NOTE = """
## 本轮是总结/结论类请求,额外要求
- 先对照上方载入的本场数据逐条核对前文要点,再写总结。前文某句与数据不符、或后来已被更正的,不要照抄,直接按数据写并说明"此处已按数据更正"。
- 涉及亚盘上盘/下盘、赢半输半的表述,只按上方【盘口读法】里的结算写,不要自己现推。
- 没有载入数据支撑的要点(来自联网或记忆),要标"未经本场数据核对",不要和有数据支撑的结论放在同等地位。
- 如果上方提示盘口数据抓取已滞后,总结里必须带上这一点,不要写成"盘口已消化某信息"。
"""


def wants_refresh(text: str) -> bool:
    """用户要求现抓最新盘口赔率(如"抓取本场最新的盘口赔率并分析")。需同时有"最新/抓取"类动作词和盘口赔率对象。"""
    t = text or ""
    return bool(_REFRESH_ACT.search(t) and _REFRESH_OBJ.search(t))


def refresh_note(res: Dict[str, Any]) -> str:
    """本次实时抓取的结果说明, 放进数据区, 让模型如实告知用户数据新旧。"""
    if res.get("ok"):
        part = f"(其中 {len(res['failed'])} 项请求失败: {', '.join(res['failed'][:6])})" if res.get("failed") else ""
        cached = "(2 分钟内刚抓过,复用该结果)" if res.get("cached") else ""
        return (f"【本次实时抓取】已于北京时间 {res['fetchedAt'][5:16]} 从 500.com 抓取最新盘口赔率{cached},"
                f"成功 {res['got']} 项{part},新增/更新 {res['ticks']} 个变动点。上方「其他公司逐次变动」和「Bet365 亚盘逐次变动」是刚抓到的最新数据,"
                "以其最后一条为即时盘;而「亚盘/欧赔/大小球 初盘→即时盘」汇总来自定时缓存,可能比逐次变动旧,有出入时以逐次变动为准。"
                "回答时先说明数据抓取时间,并指出相较之前的主要变化(如果能从逐次变动看出)。")
    from odds500_live import REASON_TEXT
    why = REASON_TEXT.get(res.get("reason"), "未知原因")
    return (f"【本次实时抓取失败】原因:{why}。上方盘口赔率数据是之前定时抓取的结果,不是最新的,"
            "回答时必须先如实告诉用户这次没有抓到最新数据,并写明上方数据各自的抓取/最新变动时间。")


def wanted_sections(text: str) -> List[str]:
    """用户这句话要求关联哪些本场数据。需要明确的关联意图(关联/结合…或指明本场),避免日常提问误触发。"""
    t = text or ""
    if _ALL_RE.search(t) and (_CUE_RE.search(t) or _SCOPE_RE.search(t)):
        return list(_SEC_RE.keys())
    if not (_CUE_RE.search(t) or _SCOPE_RE.search(t)):
        return []
    return [k for k, rx in _SEC_RE.items() if rx.search(t)]


WEB_ON_NOTE = """
## 联网已开启
用户打开了联网搜索。当问题涉及需要最新信息的内容(预计/官方首发、伤停、停赛、复出、新闻、天气、积分形势、近期动态等)时,必须先用 web_search 查,不要凭记忆回答。
- 搜索关键词用队名加开赛日期,例如"西悉尼流浪者 阿德莱德联 首发 伤停 11月20日";一次没搜到可换关键词或用英文再搜。
- 只采信与本场直接相关、开赛前近期发布的内容;回答里标注来源站点和日期;多个来源冲突或只有单一来源时要说明。
- 搜了仍然没有,就明确说"联网也没查到",并说明大概什么时候会公布。
- 纯知识性或只涉及已载入数据的问题不用搜。
"""


def check_quota(user_id: int) -> bool:
    key = (user_id, time.strftime("%Y-%m-%d"))
    if _usage[key] >= DAILY_LIMIT:
        return False
    _usage[key] += 1
    return True


def _hist_messages(user_id: int, match_id: str) -> List[Dict[str, Any]]:
    rows = store.list_messages(user_id, match_id, limit=HISTORY_LIMIT)
    msgs: List[Dict[str, Any]] = []
    for r in rows:
        if not r["content"]:
            continue
        if msgs and msgs[-1]["role"] == r["role"]:      # 中断遗留的连续同角色消息合并
            msgs[-1]["content"] += "\n\n" + r["content"]
        else:
            msgs.append({"role": r["role"], "content": r["content"]})
    while msgs and msgs[0]["role"] != "user":
        msgs.pop(0)
    return msgs


def run_turn(user_id: int, match_id: str, text: str, images: List[Dict[str, str]],
             web: bool = False, persist: bool = True) -> Iterator[Dict[str, Any]]:
    """产出事件 dict: status/delta/sources/verdict/done/error。"""
    history = _hist_messages(user_id, match_id) if persist else []
    want: List[str] = []
    for t in [h["content"] for h in history if h["role"] == "user" and isinstance(h["content"], str)] + [text]:
        for k in wanted_sections(t):          # 本会话里提过的关联一直保留
            if k not in want:
                want.append(k)
    # 实时抓取: 用户明确要求, 或已关联盘口且临近开赛数据已滞后(自动)
    refresh = None
    reason = None
    if wants_refresh(text):
        reason = "正在抓取最新盘口赔率(约 15-30 秒)…"
    elif "odds" in want:
        try:
            from .context import market_freshness
            fr = market_freshness(match_id)
            eta, age = fr.get("eta"), fr.get("ageMin")
            if eta is not None and 0 < eta <= AUTO_REFRESH_WITHIN and (age is None or age > AUTO_REFRESH_STALE_MIN):
                reason = f"盘口数据已落后{'' if age is None else f' {age} 分钟'},临近开赛,正在自动抓取最新数据(约 15-30 秒)…"
        except Exception as e:  # noqa: BLE001
            logger.warning("新鲜度检查失败 %s: %s", match_id, e)
    if reason:
        yield {"type": "status", "text": reason}
        try:
            from odds500_live import refresh_match_odds
            refresh = refresh_match_odds(match_id)
        except Exception as e:  # noqa: BLE001  抓取异常不影响聊天
            logger.warning("实时抓取异常 %s: %s", match_id, e)
            refresh = {"ok": False, "reason": "exception"}
        yield {"type": "status", "text": ("最新盘口赔率已抓取" if refresh.get("ok") else "实时抓取未成功,使用已有数据")}
    ctx = build_context(match_id)
    if refresh is not None and "odds" not in want:
        want.append("odds")
    secs = ctx["sections"]
    want = [k for k in want if secs.get(k)]
    body = "\n\n".join([secs[k] for k in want])
    data = DATA_RULES.format(now=datetime.now().strftime("%Y-%m-%d %H:%M"), body=body) if body else ""
    if refresh is not None:
        data += "\n" + refresh_note(refresh) + "\n"
    _id = (secs.get("id") or "").split("\n")
    ident = (_id[1] if len(_id) > 1 else "") or f"{ctx['home']} vs {ctx['away']}"
    system = SYSTEM_TMPL.format(ident=ident, data=data)
    if web:
        system += WEB_ON_NOTE
    if wants_summary(text):
        system += SUMMARY_NOTE
    if want:
        yield {"type": "attached", "sections": [SECTION_LABEL[k] for k in want]}

    content: Any = text
    if images:
        content = [{"type": "image", "source": {"type": "base64", "media_type": im["media_type"], "data": im["data"]}}
                   for im in images] + [{"type": "text", "text": text or "请结合这些图片分析本场比赛。"}]
    messages = history + [{"role": "user", "content": content}]

    if persist:
        store.add_message(user_id, match_id, "user", text or "(仅图片)", attachments_n=len(images), ctx_hash=ctx["hash"])

    buf: List[str] = []
    sources: List[Dict[str, str]] = []
    usage: Dict[str, Any] = {}
    failed = False
    saved = False
    try:
        for ev in stream_chat(system, messages, web=web):
            t = ev["type"]
            if t == "delta":
                buf.append(ev["text"])
                yield ev
            elif t == "sources":
                sources = ev["items"]
                if sources:
                    yield ev
            elif t == "usage":
                usage = ev["usage"]
            elif t == "error":
                failed = True
                yield ev
            else:
                yield ev
        full = "".join(buf)
        if failed and not full:
            return
        clean = full.strip()
        mid = None
        if persist and clean:
            mid = store.add_message(user_id, match_id, "assistant", clean, sources=sources,
                                    web_used=bool(sources), ctx_hash=ctx["hash"])
            saved = True
        if usage.get("stop_reason") == "max_tokens":
            yield {"type": "notice", "text": "回答因长度上限被截断,点下方「继续」可接着生成,或缩小问题范围"}
        yield {"type": "done", "messageId": mid, "text": clean, "usage": usage}
    finally:
        # 客户端中途断开/停止: 保存已生成的部分,避免历史里只剩悬空的提问
        if persist and not saved and buf:
            partial = "".join(buf).strip()
            if partial:
                try:
                    store.add_message(user_id, match_id, "assistant", partial + "\n\n(回答被中断)",
                                      sources=sources, web_used=bool(sources), ctx_hash=ctx["hash"])
                except Exception:  # noqa: BLE001
                    pass
