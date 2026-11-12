"""DeepSeek Anthropic 兼容接口(/anthropic/v1/messages)流式调用,支持服务端联网搜索。

用原始 httpx 解析 SSE,不依赖 anthropic SDK 对 server_tool_use 事件的支持程度。
事件产出(dict): status / delta / sources / usage / error
"""
from __future__ import annotations

import json
import os
from typing import Any, Dict, Iterator, List, Optional

import httpx

BASE = os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com").rstrip("/")
MODEL = os.getenv("MATCH_CHAT_MODEL", "deepseek-flash")
MAX_TOKENS = int(os.getenv("MATCH_CHAT_MAX_TOKENS", "16000"))
WEB_MAX_USES = int(os.getenv("MATCH_CHAT_WEB_MAX_USES", "3"))


def _headers() -> Dict[str, str]:
    key = (os.getenv("DEEPSEEK_API_KEY") or "").strip()
    if not key:
        raise RuntimeError("DEEPSEEK_API_KEY 未配置")
    return {"x-api-key": key, "anthropic-version": "2023-06-01", "content-type": "application/json"}


def stream_chat(system: str, messages: List[Dict[str, Any]], web: bool = True) -> Iterator[Dict[str, Any]]:
    body: Dict[str, Any] = {"model": MODEL, "max_tokens": MAX_TOKENS, "system": system,
                            "messages": messages, "stream": True}
    if web:
        body["tools"] = [{"type": "web_search_20250305", "name": "web_search", "max_uses": WEB_MAX_USES}]
    sources: List[Dict[str, str]] = []
    seen = set()
    blocks: Dict[int, Dict[str, Any]] = {}
    usage: Dict[str, Any] = {}
    try:
        with httpx.stream("POST", f"{BASE}/anthropic/v1/messages", headers=_headers(),
                          json=body, timeout=httpx.Timeout(30.0, read=180.0)) as r:
            if r.status_code != 200:
                yield {"type": "error", "text": f"模型接口错误 {r.status_code}: {r.read().decode()[:200]}"}
                return
            event = None
            for line in r.iter_lines():
                if not line:
                    continue
                if line.startswith("event:"):
                    event = line[6:].strip()
                    continue
                if not line.startswith("data:"):
                    continue
                try:
                    d = json.loads(line[5:].strip())
                except json.JSONDecodeError:
                    continue
                t = d.get("type") or event
                if t == "content_block_start":
                    idx = d.get("index", 0)
                    cb = d.get("content_block") or {}
                    blocks[idx] = {"type": cb.get("type"), "name": cb.get("name"), "json": ""}
                    if cb.get("type") == "thinking":
                        yield {"type": "status", "text": "思考中"}
                    elif cb.get("type") == "web_search_tool_result":
                        for x in (cb.get("content") or []):
                            if isinstance(x, dict) and x.get("type") == "web_search_result":
                                u = x.get("url")
                                if u and u not in seen:
                                    seen.add(u)
                                    sources.append({"title": (x.get("title") or u)[:120], "url": u})
                        yield {"type": "status", "text": f"已获取 {len(sources)} 条联网来源"}
                elif t == "content_block_delta":
                    idx = d.get("index", 0)
                    dl = d.get("delta") or {}
                    if dl.get("type") == "text_delta":
                        yield {"type": "delta", "text": dl.get("text", "")}
                    elif dl.get("type") == "input_json_delta" and idx in blocks:
                        blocks[idx]["json"] += dl.get("partial_json", "")
                elif t == "content_block_stop":
                    b = blocks.get(d.get("index", 0)) or {}
                    if b.get("type") == "server_tool_use" and b.get("json"):
                        try:
                            q = json.loads(b["json"]).get("query")
                        except json.JSONDecodeError:
                            q = None
                        if q:
                            yield {"type": "status", "text": f"联网搜索: {q[:60]}"}
                elif t == "message_delta":
                    usage.update(d.get("usage") or {})
                    if (d.get("delta") or {}).get("stop_reason"):
                        usage["stop_reason"] = d["delta"]["stop_reason"]
                elif t == "message_start":
                    usage.update(((d.get("message") or {}).get("usage")) or {})
                elif t == "error":
                    yield {"type": "error", "text": str((d.get("error") or {}).get("message") or "模型错误")[:200]}
                    return
    except httpx.HTTPError as e:
        yield {"type": "error", "text": f"模型连接失败: {type(e).__name__}"}
        return
    yield {"type": "sources", "items": sources}
    yield {"type": "usage", "usage": usage}
