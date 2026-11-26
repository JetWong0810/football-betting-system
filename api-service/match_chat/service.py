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
DAILY_LIMIT = int(__import__("os").getenv("MATCH_CHAT_DAILY_LIMIT", "0"))   # 0 = 不限制; 需要限额时设环境变量

_usage: Dict[tuple, int] = defaultdict(int)   # (user_id, YYYY-MM-DD) -> n;进程内,重启清零


SYSTEM_TMPL = """你是一位足球分析助手(盘路、赔率、基本面),像普通聊天助手一样回答用户的问题。

当前讨论的比赛:{ident}

回答方式:
- 自然、直接地回答,可以用 Markdown(分点、加粗、表格),不套模板,不要刻意压缩也不要冗长;先回答问的问题。
- 默认不使用任何本场的系统数据,依靠你自己的知识和(开启时的)联网搜索回答。联网查到的内容要标注来源站点和日期;来源冲突、单一来源或搜不到时要如实说明,不要编造。
- 系统具备实时抓取最新盘口赔率的能力:用户说"抓取本场最新的盘口赔率"等时,系统会在你回答之前自动执行抓取,结果在下方数据区的「本次实时抓取」里。不要说你自己没有抓取工具;如果下方没有「本次实时抓取」的说明,说明这一句没有触发抓取,提醒用户用"抓取本场最新的盘口赔率数据"这样的说法再试。
- 用户可以说"请关联本场的某某数据"来载入系统数据,可载入的有:盘口赔率(多家公司亚盘、欧赔、大小球及赔率变动)、历史同赔、七因子预测、交锋历史、近期战绩与赛程、关联文章,或"本场全部数据"。载入后,下方会出现对应的「本场数据」,你必须基于这些数据回答,引用的数字、比分、日期要与数据一致。
- 如果用户的问题明显需要本场系统数据、但下方没有载入,就先用你自己的知识/联网回答能答的部分,并简短提示"如需结合本场XX数据,请说'请关联本场XX数据'",不要假装看过。
- 仅供参考,不构成投注建议,不要每次都重复这句话;不迎合,用户追问"是不是该买某方"时依据证据回答,不因追问改口。

用户的最终目的:判断本场让球是上盘还是下盘、大小球是大球还是小球、买什么盘口水位合适。每次回复都要朝这个目的推进:
- 这一轮的证据如果足以倾向某个方向,就说出倾向,并列出支持和反对的依据;如果不足以判断,就明确说"目前不确定",并说清楚卡在哪(缺什么信息、哪里互相矛盾),不要为了给结论而硬凑。
- 回复正文写完后,另起最后一行输出下一步建议,格式严格为:[[NEXT]] 问题一 || 问题二 || 问题三
  给 2~3 个用户下一步最该问的完整问题(能直接发送),按"最能减少不确定性"排序。需要本场系统数据的问题要写明"请关联本场XX数据",需要最新信息的写明"请联网查…",需要最新盘口的写"请抓取本场最新的盘口赔率数据"。已经足够下结论时,建议的问题改为"改判条件/临场该观察什么"。
  这一行是给界面解析用的,正文里不要提到它,也不要解释它。
- 分析顺序(载入盘口数据时遵守):①先读【市场先验】,它是起点,市场已计入公开信息;②只有尚未被定价的新信息(官方首发、临场伤停等,须标明来源和时间)才能改变先验,近期战绩/交锋/排名等公开基本面不要当作独立加分项;③对照【历史信号】和【同盘口水位信号】里的回测统计与样本量,不要凭直觉:回测里盘口加深后上盘赢盘率略偏低(逆势,约 2~4 个百分点),而盘口不变时上盘水位下降后上盘赢盘率偏高(顺势),两者方向相反,且都已被价格吸收、不是可直接下注的优势;④看【最优价】:相对 Pinnacle 两边期望都不为正,就明确写"价格上不下手"——方向对但价格不合算,等于没有可下手的建议。
- 给方向要克制:上盘和下盘的先验都是接近五五开(见数据区【赢盘基准】)。只有至少两类互相独立的证据(如盘口升降、多家欧赔变动、伤停/首发/新闻、历史同赔)方向一致时才给"倾向";只有一类证据、证据互相矛盾、或只是 1~3 个百分点的水位/去水概率差,就写"目前不确定"。不要因为受让方"覆盖的情形更多"(如"只要不输/不赢N球就成立")而偏向下盘——各情形概率本来就不均等,盘口已把它定价;同样也不要因为"热门/强队"偏向上盘。倾向要写出对立面的最强一条证据。
- 如果这一轮回复里对让球或大小球给出了方向判断(或明确写了"不确定"),在 [[NEXT]] 行之后再另起最后一行,格式严格为:[[V]] ah=上盘|下盘|不确定; ou=大球|小球|不确定 (没有讨论大小球就写 ou=无;完全没有讨论盘口方向就不要输出这一行)。这一行也是给界面解析用的,正文里不要提到它。

术语(涉及盘口时遵守):亚盘符号负=主让、正=主受让,上盘=让球方、下盘=受让方;spf=竞彩胜平负,nspf=竞彩让球胜平负,竞彩让球是整数,与亚盘小数让球不同,盘路分析以亚盘为准。
{data}"""

DATA_RULES = """
## 本场数据(用户已要求关联,生成于 {now})
使用规则:引用须与数据一致;【盘口读法】已按当前盘口预先算好各结果下的上盘/下盘结算,涉及上盘/下盘/赢半输半时直接引用,不要自己重算;其中的去水概率反映庄家的定价结构(上盘去水概率常态约 49%),只看"相对常态的偏离",不能当作方向依据;【赢盘基准】是历史先验,上下盘都接近五五开;【市场先验】是 Pinnacle(或多家平均)去水概率,【最优价】是各公司同盘口下的最高水位及相对 Pinnacle 的粗略期望,【历史信号】【同盘口水位信号】是本系统对盘口/水位变动的回测统计(含样本量),【同盘口历史净胜分布】是盘口相同的历史比赛的实际净胜球分布和各结算档位概率(判断受让方/让球方\"覆盖多少情形\"时必须按这里的概率,不要数情形个数),这三项都是数据区里的事实,引用时与数据一致;「数据新鲜度」提示必须遵守;【盘口】【欧赔】【大小球】是抓取到的多家公司亚盘/欧赔/大小球的初盘与即时盘及变动(竞彩赔率不在其中,口径不同),分析时要横向比较各家公司的方向是否一致、水位与赔率变化是否匹配;个别公司的初盘数据可能是源数据异常(与其他公司明显离群,如水位或盘口线偏离很大),遇到要指出并剔除后再下结论;历史同赔样本小时要结合置信区间说明不确定性;七因子预测是已存结果可能已过期,与实时盘口冲突时以实时为准;交锋/近期战绩里的"盘口"是数据源原值,符号方向不保证与本系统亚盘一致,不要据此判断历史让球方;【公众号文章】是作者观点和二手信息,不是已核实事实,引用要写明账号,事实声明只有"已证实"可当事实,"AI据文意推测"的倾向不是作者原话,样本不足的命中率不具参考性,多个号观点一致不等于独立证据。
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
    "inj": re.compile(r"伤停|伤病|伤情|缺阵|停赛|受伤|阵容缺"),
}


_REFRESH_ACT = re.compile(r"抓取|抓一下|刷新|重新抓|拉取|更新|实时|最新|即时")
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
- 总结必须给出:①让球方向(上盘/下盘/不确定,写出具体球队和盘口;证据不足一律写不确定,不要用 1~3 个百分点的去水差凑方向);②大小球方向(大/小/不确定,写出盘口线);③买什么盘口水位合适:引用上方【最优价】(各公司最高水位和相对 Pinnacle 的期望)与【水位参考】,两边期望都不为正就写\"价格上不下手\";用"你判断有效胜率为多少时,港式水位至少要多少才不亏"来说明,并对照当前水位说明现价是否够;不得自己编造收益率;④改判条件:列出 2~3 个出现就应改判的信号(如首发缺阵、升降盘、水位变动)。无法判断的那一项就写"不确定"并说明缺什么,不要硬给方向。
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
                "回答时先说明数据抓取时间,并指出相较之前的主要变化(如果能从逐次变动看出)。"
                "这次抓取是系统在用户提问时已经替用户执行完的,不是你的能力:不要说自己无法抓取、没有抓取工具,也不要说只能用旧数据;"
                + ("本场已开赛,开赛之后的滚球变动已被剔除,再抓只会补全到开赛前的最终盘口,不会有赛中数据,用户若要求'开赛后再抓',如实说明这一点;" if res.get("started") else "")
                + "用户若想要更新的数据,可以过一两分钟再说一次\"抓取本场最新的盘口赔率数据\"(2 分钟内重复抓取会复用刚抓的结果)。")
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


BD_NOTE = """
## 本场是北单(非竞彩)场次
- 本场没有历史同赔、七因子预测、关联公众号文章;不要提这些,用户问到就说明北单场次不提供。可载入的只有:盘口赔率(多家公司亚盘/欧赔/大小球及逐次变动)、交锋历史、近期战绩、未来赛程、赛前联赛积分。
- 这些数据都不是定时抓取的,而是用户要求时才实时抓取并存库:说"抓取本场最新的盘口赔率数据"会抓盘口赔率,说"请关联本场交锋和近期战绩"会抓交锋/战绩/赛程/积分。数据区没有对应内容时,提示用户用这样的说法。
- 预计阵容、首发、阵型、伤停、停赛、赛前新闻和发言系统不抓取,请用 web_search 联网查,并标注来源站点和日期;搜不到就说没查到。
"""


_V_RE = re.compile(r"\[\[V\]\]\s*ah\s*=\s*([^;\n]*?)\s*[;；]\s*ou\s*=\s*([^\n]*)")


def extract_verdict(text: str):
    """取出模型输出的 [[V]] 结构化倾向行, 返回 (去掉该行后的正文, verdict dict 或 None)。"""
    m = _V_RE.search(text or "")
    if not m:
        return re.sub(r"\n?\[\[V\]\][^\n]*", "", text or "").rstrip(), None
    norm = lambda x: x.strip().replace("盘", "盘").strip(" 。") or "无"
    clean = (text[:m.start()] + text[m.end():]).rstrip()
    return clean, {"ah": norm(m.group(1)), "ou": norm(m.group(2))}


def check_quota(user_id: int) -> bool:
    if DAILY_LIMIT <= 0:
        return True
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
    bd = match_id.startswith("bd_")
    if bd and not reason and "odds" in want:        # 北单无定时抓取: 首次关联盘口时(库里一条都没有)自动抓一次
        try:
            from .context import market_freshness
            fr = market_freshness(match_id)
            if not any(v.get("lastFetch") for v in (fr.get("kinds") or {}).values()):
                reason = "本场盘口赔率还没抓取过,正在实时抓取(约 15-30 秒)…"
        except Exception as e:  # noqa: BLE001
            logger.warning("北单新鲜度检查失败 %s: %s", match_id, e)
    fenxi = None
    if bd and ({"h2h", "recent"} & set(want)):
        import bd_service
        yield {"type": "status", "text": "正在抓取交锋/近期战绩/赛程…"}
        try:
            fenxi = bd_service.fetch_fenxi(match_id)
        except Exception as e:  # noqa: BLE001
            logger.warning("北单数据页抓取异常 %s: %s", match_id, e)
            fenxi = {"ok": False, "reason": "error"}
    inj_res = None
    if "inj" in want and not bd:
        try:
            from api_football import injuries as af_inj
            inj_res = af_inj.fetch(match_id)
        except Exception as e:  # noqa: BLE001  伤停抓取失败不影响聊天
            logger.warning("伤停抓取异常 %s: %s", match_id, e)
            inj_res = {"ok": False, "reason": "error"}
        yield {"type": "status", "text": "伤停已更新" if (inj_res or {}).get("ok") else "伤停没有抓到,使用已有数据"}
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
    if inj_res is not None and not inj_res.get("ok"):
        why = "本场还没有对应到 API-Football 的比赛" if inj_res.get("reason") == "no_mapping" else "接口请求失败"
        data += (f"\n【本次抓取伤停失败】原因:{why}。回答时如实告诉用户没有拿到伤停数据(若上方【伤停】有内容则是之前存的旧数据,须注明抓取时间),"
                 "不要凭印象补写伤停;可以建议用户打开联网搜索查伤停。\n")
    if fenxi is not None and not fenxi.get("ok"):
        import bd_service
        data += (f"\n【本次抓取交锋/战绩失败】原因:{bd_service.FENXI_REASON.get(fenxi.get('reason'), '未知')}。"
                 "回答时如实告诉用户没有抓到,数据区里的交锋/战绩(若有)是之前存的旧数据。\n")
    _id = (secs.get("id") or "").split("\n")
    ident = (_id[1] if len(_id) > 1 else "") or f"{ctx['home']} vs {ctx['away']}"
    system = SYSTEM_TMPL.format(ident=ident, data=data)
    if bd:
        system += BD_NOTE
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
        clean, verdict = extract_verdict(full.strip())
        mid = None
        if persist and clean:
            if verdict and ctx.get("snap"):
                verdict["snap"] = ctx["snap"]          # 倾向发出时的盘口与水位, 用于之后结算与盈亏统计
            mid = store.add_message(user_id, match_id, "assistant", clean, sources=sources, verdict=verdict,
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
