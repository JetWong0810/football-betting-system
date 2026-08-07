"""日文 → 中文展示名（队名/场馆/球员）。"""
from __future__ import annotations

import json
import logging
import os
import re
from typing import Dict, List, Optional

from openai import OpenAI

import settings  # noqa: F401  — 加载 .env
from .aliases import J1_CLUB_SEEDS
from .db import get_conn, ensure_schema

logger = logging.getLogger(__name__)

# 简称 → 中文惯用名（取种子别名里第一个中文）
CLUB_ZH: Dict[str, str] = {}
for short, _slug, als, _comp in J1_CLUB_SEEDS:
    zh = next((a for a in als if re.search(r"[\u4e00-\u9fff]", a) and not re.search(r"[ぁ-んァ-ン]", a)), None)
    if zh:
        CLUB_ZH[short] = zh
    for a in als:
        if re.search(r"[ぁ-んァ-ン・]", a) or "Ｆ" in a or "Ｃ" in a:
            if zh:
                CLUB_ZH[a] = zh
CLUB_ZH["ガンバ大阪"] = "大阪钢巴"
CLUB_ZH["浦和レッズ"] = "浦和红钻"
CLUB_ZH["鹿島アントラーズ"] = "鹿岛鹿角"
CLUB_ZH["横浜F・マリノス"] = "横滨水手"
CLUB_ZH["横浜Ｆ・マリノス"] = "横滨水手"
CLUB_ZH["G大阪"] = "大阪钢巴"
CLUB_ZH["浦和"] = "浦和红钻"

VENUE_ZH = {
    "パナスタ": "吹田松下球场",
    "MUFG国立": "国立竞技场",
    "日産ス": "横滨日产球场",
    "味スタ": "东京味之素球场",
    "豊田ス": "丰田球场",
    "Ｅピース": "广岛和平球场",
    "三協Ｆ柏": "柏三协球场",
    "ベススタ": "福冈银行穹顶",
    "ノエスタ": "神户诺埃维亚球场",
    "等々力": "川崎等力球场",
    "国立": "国立竞技场",
    "埼玉ス": "埼玉2002球场",
    "デンカＳ": "新潟电化大体育场",
    "アイスタ": "清水IAI球场",
    "レモンＳ": "山口柠檬体育场",
    "ＮＡＣＫ": "大宫NACK5球场",
    "町田ＧＩＯＮ": "町田GION球场",
    "ＪＱスタ": "冈山JQ球场",
    "サンアル": "鸟栖最佳电器球场",
    "維新公園": "山口维新公园",
}

# 日文汉字 → 简体
_KANJI_REPL = [
    ("鈴木", "铃木"), ("渡邊", "渡边"), ("斎藤", "斋藤"), ("齋藤", "斋藤"),
    ("高橋", "高桥"), ("後藤", "后藤"), ("岡田", "冈田"), ("福島", "福岛"),
    ("広瀬", "广濑"), ("黒崎", "黑崎"), ("黒田", "黑田"), ("宮本", "宫本"),
    ("邊", "边"), ("浜", "滨"), ("沢", "泽"), ("竜", "龙"), ("徳", "德"),
    ("読", "读"), ("関", "关"), ("戦", "战"), ("観", "观"), ("実", "实"),
    ("発", "发"), ("経", "经"), ("験", "验"), ("駅", "驿"), ("戸", "户"),
    ("剣", "剑"), ("長", "长"), ("島", "岛"), ("橋", "桥"), ("樹", "树"),
    ("楽", "乐"), ("気", "气"), ("桜", "樱"), ("瑠", "琉"), ("純", "纯"),
    ("優", "优"), ("勝", "胜"), ("眞", "真"), ("湊", "凑"), ("誉", "誉"),
    ("駿", "骏"), ("進", "进"), ("諒", "谅"), ("飛", "飞"), ("絢", "绚"),
    ("銀", "银"), ("宮", "宫"), ("黒", "黑"), ("斎", "斋"), ("嶋", "岛"),
    ("瀬", "濑"), ("岡", "冈"), ("広", "广"), ("暁", "晓"), ("勲", "勋"),
    ("児", "儿"), ("曽", "曾"), ("亀", "龟"), ("齢", "龄"), ("庁", "厅"),
    ("横浜", "横滨"), ("豊", "丰"), ("協", "协"), ("々", ""),
    ("龍", "龙"), ("澤", "泽"), ("廣", "广"), ("國", "国"),
    ("偉", "伟"), ("達", "达"), ("彌", "弥"), ("壽", "寿"), ("堯", "尧"),
    ("彥", "彦"), ("聰", "聪"), ("遙", "遥"), ("齊", "齐"),
    ("倫", "伦"), ("聖", "圣"), ("誠", "诚"),
    ("貴", "贵"), ("輝", "辉"), ("颯", "飒"), ("蓮", "莲"), ("涼", "凉"),
    ("諏", "诹"), ("訪", "访"), ("慶", "庆"), ("飯", "饭"), ("陸", "陆"),
    ("間", "间"), ("倉", "仓"), ("祐", "佑"), ("舘", "馆"), ("峯", "峰"),
]

_KANA = re.compile(r"[ぁ-んァ-ン･・]")
# 繁简后仍可能残留的日文特有字形
_JP_RESIDUAL = re.compile(
    r"[ぁ-んァ-ン･・邊黒斎龍澤徳廣進諒飛絢銀宮嶋瀬岡暁勲児曽亀齢庁横浜豊偉倫聖]"
)


def club_zh(name: Optional[str]) -> str:
    if not name:
        return ""
    if name in CLUB_ZH:
        return CLUB_ZH[name]
    return CLUB_ZH.get(name.strip(), _kanji_to_simp(name))


def venue_zh(name: Optional[str]) -> str:
    if not name:
        return ""
    if name in VENUE_ZH:
        return VENUE_ZH[name]
    return _kanji_to_simp(name)


def source_zh(source: Optional[str]) -> str:
    return {
        "gekisaka": "日媒临场首发",
        "sfms02": "官网公式记录",
        "open_meteo": "天气预报",
    }.get(source or "", source or "")


def lineup_source_zh(label: Optional[str]) -> str:
    if not label:
        return ""
    if "ゲキサカ" in label or "gekisaka" in label.lower():
        return "日媒临场首发"
    if "公式" in label or "sfms" in label.lower():
        return "官网公式记录"
    return label


def _kanji_to_simp(s: str) -> str:
    out = s or ""
    for a, b in _KANJI_REPL:
        out = out.replace(a, b)
    return out


def _ensure_player_name_table(cur) -> None:
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS jp_player_names (
          name_ja VARCHAR(128) NOT NULL PRIMARY KEY,
          name_zh VARCHAR(128) NOT NULL,
          source VARCHAR(32) DEFAULT 'deepseek',
          updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
        """
    )


def _lookup_zh(cur, names: List[str]) -> Dict[str, str]:
    if not names:
        return {}
    out = {}
    for i in range(0, len(names), 50):
        chunk = names[i:i + 50]
        ph = ",".join(["%s"] * len(chunk))
        cur.execute(f"SELECT name_ja, name_zh FROM jp_player_names WHERE name_ja IN ({ph})", chunk)
        for r in cur.fetchall() or []:
            out[r["name_ja"]] = r["name_zh"]
    return out


def _save_zh(cur, mapping: Dict[str, str], source: str = "deepseek") -> None:
    for ja, zh in mapping.items():
        if not ja or not zh:
            continue
        cur.execute(
            "INSERT INTO jp_player_names (name_ja, name_zh, source) VALUES (%s,%s,%s) "
            "ON DUPLICATE KEY UPDATE name_zh=VALUES(name_zh), source=VALUES(source)",
            (ja, zh, source),
        )


def _heuristic_zh(name: str) -> Optional[str]:
    if not name:
        return None
    if re.search(r"[ァ-ンA-Za-z･・]", name):
        return None
    simp = _kanji_to_simp(name)
    if _KANA.search(simp):
        return None
    return simp


def _still_looks_jp(s: str) -> bool:
    return bool(_JP_RESIDUAL.search(s or ""))


def _parse_json_obj(text: str) -> Dict[str, str]:
    text = (text or "").strip()
    if not text:
        return {}
    if text.startswith("```"):
        text = text.split("\n", 1)[-1]
        if text.endswith("```"):
            text = text[:-3]
        text = text.strip()
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        m = re.search(r"\{[\s\S]*\}", text)
        if not m:
            return {}
        data = json.loads(m.group(0))
    if not isinstance(data, dict):
        return {}
    for key in ("translations", "names", "result", "data"):
        if isinstance(data.get(key), dict):
            data = data[key]
            break
    return {str(k): str(v).strip() for k, v in data.items() if v and str(v).strip()}


def _deepseek_translate_chunk(client: OpenAI, model: str, names: List[str]) -> Dict[str, str]:
    prompt = (
        "将下列日本职业足球球员姓名译为中文体育媒体惯用译名（简体）。"
        "外国人名用常见音译；日本人名用简体汉字惯用写法。"
        "只输出JSON对象，键为原文、值为中文，不要其它文字。\n"
        + json.dumps(names, ensure_ascii=False)
    )
    last_err = None
    for use_json_fmt in (True, False):
        try:
            kwargs = {}
            if use_json_fmt:
                kwargs["response_format"] = {"type": "json_object"}
            resp = client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": "你是足球译名助手，只输出JSON。"},
                    {"role": "user", "content": prompt},
                ],
                temperature=0.1,
                max_tokens=2048,
                **kwargs,
            )
            text = (resp.choices[0].message.content or "").strip()
            parsed = _parse_json_obj(text)
            if parsed:
                return parsed
            last_err = f"空/非JSON: {text[:120]!r}"
        except Exception as e:
            last_err = str(e)
            continue
    logger.warning("DeepSeek 球员译名失败(%d名): %s", len(names), last_err)
    return {}


def _deepseek_translate(names: List[str]) -> Dict[str, str]:
    if not names:
        return {}
    api_key = os.getenv("DEEPSEEK_API_KEY", "")
    if not api_key:
        logger.warning("无 DeepSeek key，跳过球员译名")
        return {}
    client = OpenAI(api_key=api_key, base_url=os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com"))
    model = os.getenv("DEEPSEEK_MODEL", "deepseek-v4-flash")
    out: Dict[str, str] = {}
    for i in range(0, len(names), 15):
        chunk = names[i:i + 15]
        out.update(_deepseek_translate_chunk(client, model, chunk))
    return out


def resolve_player_names_zh(names: List[str], apply: bool = True) -> Dict[str, str]:
    """批量日文球员名 → 中文；写缓存表。"""
    uniq = []
    seen = set()
    for n in names:
        n = (n or "").strip()
        if not n or n in seen:
            continue
        seen.add(n)
        uniq.append(n)
    if not uniq:
        return {}

    ensure_schema(apply=apply)
    conn = get_conn()
    result: Dict[str, str] = {}
    try:
        with conn.cursor() as cur:
            _ensure_player_name_table(cur)
            cached = _lookup_zh(cur, uniq)
            usable = {}
            stale = []
            for ja, zh in cached.items():
                zh2 = _kanji_to_simp(zh or "")
                if _still_looks_jp(zh2) or _KANA.search(zh2):
                    stale.append(ja)
                else:
                    usable[ja] = zh2
                    if zh2 != zh and apply:
                        _save_zh(cur, {ja: zh2}, source="kanji_simp")
            if stale and apply:
                ph = ",".join(["%s"] * len(stale))
                cur.execute(f"DELETE FROM jp_player_names WHERE name_ja IN ({ph})", stale)
                conn.commit()
            elif apply:
                conn.commit()
            result.update(usable)
            missing = [n for n in uniq if n not in result]

            heur: Dict[str, str] = {}
            still: List[str] = []
            for n in missing:
                if re.search(r"[ァ-ンA-Za-z･・]", n):
                    still.append(n)
                    continue
                h = _heuristic_zh(n) or _kanji_to_simp(n)
                if h and not _still_looks_jp(h):
                    heur[n] = h
                else:
                    still.append(n)
            if heur and apply:
                _save_zh(cur, heur, source="kanji_simp")
                conn.commit()
            result.update(heur)

            if still and apply:
                translated = _deepseek_translate(still)
                fixed = {k: _kanji_to_simp(v.strip()) for k, v in translated.items() if v and str(v).strip()}
                if fixed:
                    _save_zh(cur, fixed, source="deepseek")
                    conn.commit()
                    result.update(fixed)
    finally:
        conn.close()

    for n in uniq:
        if n not in result:
            result[n] = _kanji_to_simp(n)
        else:
            result[n] = _kanji_to_simp(result[n])
    return result
