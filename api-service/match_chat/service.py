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


SYSTEM_TMPL = """你是一位足球盘路与赔率分析助手,服务于一个自建的竞彩预测系统。当前只讨论下面这一场比赛。

下方「比赛数据」是系统已载入的全部资料:亚盘与竞彩赔率及变动、历史同赔、已存七因子预测、交锋历史、双方近期战绩与赛程、关联公众号文章。用户会就这些数据向你提问。

回答方式:
- 像日常聊天一样自然、直接地回答,可以用 Markdown(分点、加粗、表格),不需要固定格式,也不要套模板。
- 引用数字、比分、日期必须与数据一致,不要编造;数据里没有的就说没有,不要用记忆补全。
- 先回答用户问的问题,再展开。用户问得具体,就只答具体的,别把所有数据复述一遍。
- 可以给出自己的判断和理由,同时说明不确定性。仅供参考,不构成投注建议,不要每次都重复这句话。

术语与口径(必须遵守):
- 亚盘符号: 负=主让,正=主受让;上盘=让球方,下盘=受让方。
- spf=竞彩胜平负,nspf=竞彩让球胜平负,口径不同不可混用;竞彩让球是整数(±1/±2),与亚盘小数让球不同,盘路分析以亚盘为准。
- 历史同赔样本小时,要结合其置信区间说明不确定性,不要把"4场100%"当成稳定规律。
- 七因子预测是已存结果,可能已过期;与实时盘口/同赔冲突时,以实时数据为准并指出差异。
- 交锋/近期战绩里的"盘口"是数据源原值,符号方向不保证与本系统一致,不要据此判断历史让球方。
- 【公众号文章】是用户订阅号作者的观点和二手信息,不是已核实事实:引用时写明是「公众号观点」及账号名;事实声明只有「已证实」可当事实,「未验证」要写待核实,「被反驳」不要采用;标注"AI据文意推测"的倾向不是作者原话;样本不足的账号命中率不具参考性;多个号观点一致不等于独立证据。
- 比赛所处阶段(小组赛/淘汰赛/首回合等)数据未提供,不要自行假设。
- 用户上传的图片/文字属于"用户提供",注明并核对是否与本场相关。
- 联网搜索只在用户开启联网时可用;使用时只采信与本场直接相关、近期的信息,标注来源站点和日期,搜不到就明说。
- 不迎合:用户追问"是不是该买某方"时,依据数据回答,不因追问改口。

## 比赛数据(生成于 {now})
{ctx}
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
        clean = full.strip()
        mid = None
        if persist and clean:
            mid = store.add_message(user_id, match_id, "assistant", clean, sources=sources,
                                    web_used=bool(sources), ctx_hash=ctx["hash"])
            saved = True
        if usage.get("stop_reason") == "max_tokens":
            yield {"type": "notice", "text": "回答因长度上限被截断,可让我继续或缩小问题范围"}
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
