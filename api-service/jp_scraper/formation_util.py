"""阵型解析/估算（免费源常无明文阵型，用位置人数兜底）。"""
from __future__ import annotations

import re
from typing import Any, Dict, List, Optional


_FORM_RE = re.compile(
    r"(?:フォーメーション|布陣|システム)?\s*([1-5](?:\s*[-−‐–]\s*[1-5]){2,4})"
)


def normalize_formation(raw: Optional[str]) -> Optional[str]:
    if not raw:
        return None
    s = re.sub(r"\s+", "", str(raw)).replace("−", "-").replace("‐", "-").replace("–", "-")
    if not re.fullmatch(r"[1-5](?:-[1-5]){2,4}", s):
        return None
    return s


def extract_formation_from_text(text: str) -> Optional[str]:
    """从日媒/官网正文抽明文阵型。"""
    if not text:
        return None
    for m in _FORM_RE.finditer(text):
        form = normalize_formation(m.group(1))
        if form:
            # 过滤赛季串 25-26 等：段数≥3 且总和通常 10（不含门将）
            parts = [int(x) for x in form.split("-")]
            if len(parts) >= 3 and 8 <= sum(parts) <= 11:
                return form
    return None


def formation_from_players(players: Optional[List[Dict[str, Any]]]) -> Optional[str]:
    """按首发 GK/DF/MF/FW 人数估算，如 4-5-1（不含门将）。"""
    if not players:
        return None
    df = mf = fw = gk = 0
    for p in players:
        pos = (p.get("pos") or "").upper()
        if pos == "GK":
            gk += 1
        elif pos == "DF":
            df += 1
        elif pos == "MF":
            mf += 1
        elif pos == "FW":
            fw += 1
    outfield = df + mf + fw
    if outfield < 8:
        return None
    # 标准 10 人外场；多/少人时仍按位置给出可读串
    if df == 0 or (mf == 0 and fw == 0):
        return None
    if mf and fw:
        return f"{df}-{mf}-{fw}"
    if mf:
        return f"{df}-{mf}"
    return f"{df}-{fw}"


def resolve_formation(players: Optional[List[Dict[str, Any]]],
                      explicit: Optional[str] = None,
                      text: Optional[str] = None) -> Dict[str, Any]:
    """优先明文，其次位置估算。"""
    form = normalize_formation(explicit) or extract_formation_from_text(text or "")
    if form:
        return {"formation": form, "formationEstimated": False}
    est = formation_from_players(players)
    if est:
        return {"formation": est, "formationEstimated": True}
    return {"formation": None, "formationEstimated": False}
