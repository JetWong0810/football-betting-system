"""单场聊天编排:拼系统数据 -> 流式调模型 -> 抽取结构化结论 -> 落库。"""
from __future__ import annotations

import json
import re
import time
from collections import defaultdict
from datetime import datetime
from typing import Any, Dict, Iterator, List, Optional

from . import repository as store
from .context import build_context
from .llm import stream_chat

HISTORY_LIMIT = 16            # 带入模型的历史条数
MAX_TEXT = 4000               # 单条用户消息字数上限
MAX_IMAGES = 3
MAX_IMAGE_B64 = 7_000_000     # 约 5MB 原图
DAILY_LIMIT = int(__import__("os").getenv("MATCH_CHAT_DAILY_LIMIT", "60"))

_usage: Dict[tuple, int] = defaultdict(int)   # (user_id, YYYY-MM-DD) -> n;进程内,重启清零


SYSTEM_TMPL = """你是竞彩足球盘路分析助手,服务于一个自建的预测系统。当前只讨论下面这一场比赛。

## 术语(必须遵守)
- 亚盘符号: 负=主让,正=主受让。上盘=让球方,下盘=受让方。
- spf=竞彩胜平负,nspf=竞彩让球胜平负,两者口径不同,不可混用。
- 竞彩让球是整数(±1/±2),与亚盘小数让球不同;盘路分析以亚盘为准,竞彩整数让球仅作参考。

## 证据与纪律
1. 下方「系统数据」是已核实的事实来源(盘口、历史同赔、已存七因子预测)。引用数字必须与其一致,不得编造或自创胜率/概率。
2. 同赔样本小时要明确提示不确定性(参照其置信区间),不要把"4场100%"这类说成稳定规律。
3. 七因子预测是已存结果,可能已过期;与实时盘口/同赔冲突时以实时数据为准并指出差异。
4. 你的作用是:在数据给出的方向之上,找出可能使其失效的因素(伤停、轮换、战意、赛程、临场盘口变化),并说明数据内部的矛盾。可以建议"提高/降低置信",但不要另起炉灶给出与数据无关的方向。
5. 比赛所处阶段(小组赛/淘汰赛/首回合/决赛等)系统数据未提供,不要自行假设;搜索时以队名+开赛日期为准。联网搜索只在需要核实阵容/伤停/轮换/战意等基本面时使用,且只采信与本场直接相关、开赛前近期的信息。回答中必须标注来源(站点)和日期;日期不明或单一来源要写"待核实";搜不到就明说"未查到",不要用泛泛内容凑数。联网信息只作参考,优先级低于系统数据。
6. 用户上传的图片/文字/链接内容属于"用户提供",要注明,并核对是否与本场相关、是否过期。
7. 【公众号文章】是用户订阅号的作者观点和二手信息,不是已核实事实:
   - 引用时必须写明是「公众号观点」及账号名;事实声明要带其核实状态(已证实/被反驳/未验证),只有「已证实」才可当作事实使用,「未验证」要写“待核实”,「被反驳」不得采用。
   - 作者的倾向不构成证据;标注“AI据文意推测”的倾向不是作者原话,引用时必须说明是推测;账号命中率样本不足(标注“样本不足”)时,不得据此提高置信,可以提醒用户其参考价值有限。
   - 多个公众号观点一致不等于独立证据(常互相转引)。
8. 不迎合:用户追问"是不是该买某方"时,依据证据回答,不因追问改口。仅供参考,不构成投注建议。

## 输出规则(最重要:简洁、结构化、突出重点)
- 先给结论,再给依据。不要叙述你的思考和搜索过程,不要罗列"我查了哪些页面/站点",不要复述系统数据原文。
- 日常问答:不超过150字,直接回答要点,必要时用不超过4条的短列表。不要写大标题。
- 当用户要求分析,或你给出方向判断时:
  - 正文只写1到2句「结论说明」(不超过80字):方向、置信,以及最关键的一个原因。
  - 减员名单、赛程、数据等具体内容一律放进 verdict 块(界面会渲染成卡片),正文禁止重复其中任何内容。
- 只保留影响判断的要点。次要信息、来源存疑的二手站点不必提;仅当它与结论冲突时用一句话带过。
- 语言精炼,多用短句和数字,不要大段加粗,不要长段落。
- 凡给出方向判断时,在回答最后另起一段输出机器可读结论,格式严格如下(界面自动解析隐藏):
```verdict
{{"headline":"一句话结论","direction":"upper|lower|neutral","confidence":"high|medium|low","supports":["【盘口】..."],"risks":["..."],"facts":[{{"text":"...","source":"站点","date":"MM-DD","status":"confirmed|pending"}}]}}
```
  字段要求:
  - headline: 一句话结论,不超过30字,含方向与关键理由。
  - direction: 亚盘盘路方向。upper=上盘(让球方)赢盘,lower=下盘,neutral=无明确倾向。
  - supports: 最多3条,每条不超过28字,开头用【盘口】【同赔】【多因子】【基本面】之一标注类型。
  - risks: 最多2条,每条不超过28字。
  - facts: 联网查到的、与本场直接相关且近期的关键基本面,最多4条;status 为 confirmed(多个来源一致或官方来源)或 pending(单一来源/待核实)。没联网或没查到则给空数组 []。
  没有给出方向判断时不要输出该段。

## 系统数据(生成于 {now})
{ctx}
"""

_VERDICT_RE = re.compile(r"```verdict\s*(\{.*?\})\s*```", re.S)


def split_verdict(text: str):
    m = None
    for m in _VERDICT_RE.finditer(text):
        pass
    if not m:
        return text.strip(), None
    try:
        v = json.loads(m.group(1))
    except json.JSONDecodeError:
        v = None
    clean = (text[:m.start()] + text[m.end():]).strip()
    if v and v.get("direction") not in ("upper", "lower", "neutral"):
        v = None
    if v:
        v["supports"] = [str(x)[:60] for x in (v.get("supports") or [])][:3]
        v["risks"] = [str(x)[:60] for x in (v.get("risks") or [])][:2]
        facts = []
        for f in (v.get("facts") or [])[:4]:
            if isinstance(f, dict) and f.get("text"):
                facts.append({"text": str(f["text"])[:60], "source": str(f.get("source") or "")[:30],
                              "date": str(f.get("date") or "")[:10],
                              "status": "confirmed" if f.get("status") == "confirmed" else "pending"})
        v["facts"] = facts
        v["headline"] = str(v.get("headline") or "")[:60]
    return clean, v


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
             web: bool = True, persist: bool = True) -> Iterator[Dict[str, Any]]:
    """产出事件 dict: status/delta/sources/verdict/done/error。"""
    ctx = build_context(match_id)
    system = SYSTEM_TMPL.format(now=datetime.now().strftime("%Y-%m-%d %H:%M"), ctx=ctx["text"])

    history = _hist_messages(user_id, match_id) if persist else []
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
        clean, verdict = split_verdict(full)
        if verdict:
            yield {"type": "verdict", "verdict": verdict}
        mid = None
        if persist and clean:
            mid = store.add_message(user_id, match_id, "assistant", clean, verdict=verdict, sources=sources,
                                    web_used=bool(sources), ctx_hash=ctx["hash"])
            saved = True
        if usage.get("stop_reason") == "max_tokens":
            yield {"type": "notice", "text": "回答因长度上限被截断,可让我继续或缩小问题范围"}
        yield {"type": "done", "messageId": mid, "text": clean, "usage": usage}
    finally:
        # 客户端中途断开/停止: 保存已生成的部分,避免历史里只剩悬空的提问
        if persist and not saved and buf:
            partial, _ = split_verdict("".join(buf))
            if partial:
                try:
                    store.add_message(user_id, match_id, "assistant", partial + "\n\n(回答被中断)",
                                      sources=sources, web_used=bool(sources), ctx_hash=ctx["hash"])
                except Exception:  # noqa: BLE001
                    pass
