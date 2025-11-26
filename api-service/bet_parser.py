"""投注信息解析模块

从OCR识别的文本中提取投注信息：球队、联赛、赔率、金额等
"""
import re
import logging
from typing import Dict, Any, List, Optional, Tuple
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)

# 常见联赛名称（用于关键词匹配）
LEAGUE_KEYWORDS = [
    # 欧洲五大联赛
    "英超", "英甲", "英冠", "英锦赛", "足总杯", "联赛杯",
    "西甲", "西乙", "国王杯",
    "意甲", "意乙", "意杯",
    "德甲", "德乙", "德国杯",
    "法甲", "法乙", "法国杯",
    # 欧洲赛事
    "欧冠", "欧联", "欧协联", "欧洲杯", "世界杯",
    # 中国联赛
    "中超", "中甲", "中乙", "足协杯",
    # 其他联赛
    "葡超", "荷甲", "比甲", "土超", "俄超",
    "美职", "墨西", "巴甲", "阿甲",
    "日职", "韩K", "澳超",
    # 通用关键词
    "联赛", "杯赛", "友谊赛", "热身赛"
]

# 投注类型关键词
BET_TYPE_KEYWORDS = {
    "胜平负": ["胜平负", "让胜平负", "胜负平", "让胜负平", "SPF", "三项盘"],
    "让球": ["让球", "让球盘", "让分", "亚盘", "让分盘", "Handicap"],
    "大小球": ["大小球", "总进球", "大小", "Over/Under", "进球数"]
}

# 投注方向关键词（胜平负）
DIRECTION_KEYWORDS = {
    "主胜": ["主胜", "主队胜", "胜", "主", "Home", "Win"],
    "平局": ["平", "平局", "和", "Draw"],
    "主负": ["负", "主队负", "主负", "客胜", "客队胜", "Away", "Loss"]
}


def extract_teams(text: str) -> Tuple[Optional[str], Optional[str]]:
    """从文本中提取主队和客队名称
    
    常见格式：
    - 曼联 vs 利物浦
    - 曼联 - 利物浦
    - 曼联vs利物浦
    - 曼联对利物浦
    
    Args:
        text: OCR识别的文本
        
    Returns:
        (主队, 客队) 或 (None, None)
    """
    # 多种分隔符模式
    patterns = [
        r'([^\s\d]+?)\s*vs\s*([^\s\d]+)',
        r'([^\s\d]+?)\s*VS\s*([^\s\d]+)',
        r'([^\s\d]+?)\s*对\s*([^\s\d]+)',
        r'([^\s\d]+?)\s*[-—]\s*([^\s\d]+)',
        r'([^\s\d]+?)\s+([^\s\d]+)',  # 空格分隔（最后尝试，可能误匹配）
    ]
    
    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            home_team = match.group(1).strip()
            away_team = match.group(2).strip()
            
            # 过滤掉明显不是球队名的结果
            if len(home_team) > 1 and len(away_team) > 1:
                # 移除可能的干扰字符
                home_team = re.sub(r'[^\u4e00-\u9fa5a-zA-Z\s]', '', home_team).strip()
                away_team = re.sub(r'[^\u4e00-\u9fa5a-zA-Z\s]', '', away_team).strip()
                
                if home_team and away_team:
                    logger.info(f"识别到球队: {home_team} vs {away_team}")
                    return home_team, away_team
    
    return None, None


def extract_league(text: str) -> Optional[str]:
    """从文本中提取联赛名称
    
    优化要点：
    - 兼容「足球 | 欧洲冠军联赛」这类格式，优先提取分隔符后的完整联赛名
    - 再回退到关键字匹配
    """
    # 特殊格式：足球 | 欧洲冠军联赛 / 足球·欧洲冠军联赛
    special_pattern = r"(?:足球|篮球)[\s\|｜·:：-]+([^\s\|｜·:：-]*联赛)"
    match = re.search(special_pattern, text)
    if match:
        league = match.group(1).strip()
        logger.info(f"识别到联赛(特殊格式): {league}")
        return league

    # 关键字匹配
    for keyword in LEAGUE_KEYWORDS:
        if keyword in text:
            # 尝试提取完整的联赛名称（可能包含赛季信息）
            pattern = rf'([\d\-/年]*\s*{re.escape(keyword)}[^\s]*)'
            match = re.search(pattern, text)
            if match:
                league = match.group(1).strip()
                logger.info(f"识别到联赛: {league}")
                return league
            else:
                logger.info(f"识别到联赛: {keyword}")
                return keyword

    return None


def extract_date(text: str) -> Optional[str]:
    """从文本中提取比赛日期
    
    支持格式：
    - 2025-11-30
    - 2025/11/30
    - 11月30日
    - 11-30
    - 今天、明天、后天
    
    Args:
        text: OCR识别的文本
        
    Returns:
        日期字符串(YYYY-MM-DD格式)或None
    """
    # 完整日期格式：YYYY-MM-DD 或 YYYY/MM/DD
    pattern1 = r'(\d{4})[-/](\d{1,2})[-/](\d{1,2})'
    match = re.search(pattern1, text)
    if match:
        year, month, day = match.groups()
        date_str = f"{year}-{month.zfill(2)}-{day.zfill(2)}"
        logger.info(f"识别到日期: {date_str}")
        return date_str
    
    # 月日格式：MM月DD日 或 MM-DD
    pattern2 = r'(\d{1,2})[月\-/](\d{1,2})日?'
    match = re.search(pattern2, text)
    if match:
        month, day = match.groups()
        # 使用当前年份
        year = datetime.now().year
        date_str = f"{year}-{month.zfill(2)}-{day.zfill(2)}"
        logger.info(f"识别到日期: {date_str}")
        return date_str
    
    # 相对日期
    today = datetime.now()
    if "今天" in text or "今日" in text:
        return today.strftime("%Y-%m-%d")
    elif "明天" in text or "明日" in text:
        return (today + timedelta(days=1)).strftime("%Y-%m-%d")
    elif "后天" in text:
        return (today + timedelta(days=2)).strftime("%Y-%m-%d")
    
    return None


def extract_bet_type(text: str) -> Optional[str]:
    """从文本中提取投注类型
    
    Args:
        text: OCR识别的文本
        
    Returns:
        投注类型：胜平负、让球、大小球，或None
    """
    for bet_type, keywords in BET_TYPE_KEYWORDS.items():
        for keyword in keywords:
            if keyword.lower() in text.lower():
                logger.info(f"识别到投注类型: {bet_type}")
                return bet_type
    
    return None


def extract_selection_and_odds(
    text: str,
    bet_type: Optional[str],
    home_team: Optional[str] = None,
    away_team: Optional[str] = None,
) -> Tuple[Optional[str], Optional[float]]:
    """从文本中提取投注方向和赔率

    增强点：
    - 对让球盘，优先识别「球队名 + 正负数值」形式，例如「皇家马德里 -1」
      并映射为前端使用的格式：主/客±盘口值（如「客-1」）
    
    Args:
        text: OCR识别的文本
        bet_type: 投注类型
        home_team: 主队名称（可选）
        away_team: 客队名称（可选）
        
    Returns:
        (投注方向, 赔率)
    """
    selection: Optional[str] = None
    odds: Optional[float] = None

    if bet_type == "胜平负":
        # 识别胜平负方向
        for direction, keywords in DIRECTION_KEYWORDS.items():
            for keyword in keywords:
                if keyword in text:
                    selection = direction
                    break
            if selection:
                break

    elif bet_type == "让球":
        # ------- 1. 优先匹配「球队名 + 正负盘」格式 -------
        team_patterns = []
        if home_team:
            team_patterns.append((home_team, "主"))
        if away_team:
            team_patterns.append((away_team, "客"))

        for team_name, side_label in team_patterns:
            # 例如："皇家马德里 -1"、"皇家马德里-1.5"
            pattern_team = rf"{re.escape(team_name)}\s*([+\-])\s*(\d+(?:\.\d+)?)"
            match = re.search(pattern_team, text)
            if match:
                sign, value = match.groups()
                selection = f"{side_label}{sign}{value}"
                logger.info(f"识别到让球盘口(带球队): {selection}")
                break

        # ------- 2. 回退到原有的纯盘口识别 -------
        if not selection:
            # 识别让球盘口：+0.5, -1, +1.5等
            # 使用更精确的匹配，避免匹配到日期
            pattern = r'(?:让球|Handicap)[^\d]*([+\-])(\d+(?:\.\d+)?)'
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                sign, value = match.groups()
                selection = f"{sign}{value}"
                logger.info(f"识别到让球盘口: {selection}")
            else:
                # 备用：直接搜索+/-和数字的组合
                pattern = r'([+\-])\s*(\d+(?:\.\d+)?)(?![-\d])'
                match = re.search(pattern, text)
                if match:
                    sign, value = match.groups()
                    selection = f"{sign}{value}"
                    logger.info(f"识别到让球盘口: {selection}")

    elif bet_type == "大小球":
        # 识别大小球盘口：大2.5, 小3等
        pattern = r'([大小])\s*(\d+(?:\.\d+)?)'
        match = re.search(pattern, text)
        if match:
            direction, value = match.groups()
            selection = f"{direction}{value}"
            logger.info(f"识别到大小球盘口: {selection}")

    # 提取赔率（小数格式：1.85, 2.10等）
    odds_pattern = r'(?:赔率|@|odds)?[:：\s]*(\d+\.\d{1,3})'
    odds_matches = re.findall(odds_pattern, text, re.IGNORECASE)
    if odds_matches:
        # 取第一个看起来合理的赔率（通常在1.01-100之间）
        for odds_str in odds_matches:
            odds_value = float(odds_str)
            if 1.01 <= odds_value <= 100:
                odds = odds_value
                logger.info(f"识别到赔率: {odds}")
                break

    return selection, odds


def extract_stake(text: str) -> Optional[float]:
    """从文本中提取投注金额
    
    支持格式：
    - 金额：100
    - 投注100元
    - 下注：100
    - 100元
    
    Args:
        text: OCR识别的文本
        
    Returns:
        投注金额或None
    """
    # 匹配金额关键词后面的数字
    patterns = [
        r'(?:金额|投注|下注|本金)[:：\s]*(\d+(?:\.\d{1,2})?)',
        r'(\d+(?:\.\d{1,2})?)\s*元',
        r'(\d+(?:\.\d{1,2})?)\s*¥',
    ]
    
    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            stake = float(match.group(1))
            # 过滤掉明显不合理的金额（如年份等）
            if 1 <= stake <= 1000000:
                logger.info(f"识别到投注金额: {stake}")
                return stake
    
    return None


def parse_bet_info(text: str, ocr_details: Optional[List[Dict]] = None) -> Dict[str, Any]:
    """解析投注信息（主函数）
    
    Args:
        text: OCR识别的完整文本
        ocr_details: OCR详细结果（包含每行文本和置信度）
        
    Returns:
        {
            "legs": [赛事列表],
            "stake": 投注金额,
            "parlayType": 串关方式（可选）,
            "confidence": 整体置信度
        }
    """
    # 提取各项信息
    home_team, away_team = extract_teams(text)
    league = extract_league(text)
    match_date = extract_date(text)
    bet_type = extract_bet_type(text) or "胜平负"  # 默认胜平负
    selection, odds = extract_selection_and_odds(text, bet_type, home_team=home_team, away_team=away_team)
    stake = extract_stake(text)
    
    # 构建返回结果
    legs = []
    
    if home_team and away_team:
        leg = {
            "homeTeam": home_team,
            "awayTeam": away_team,
            "league": league or "",
            "matchDate": match_date or datetime.now().strftime("%Y-%m-%d"),
            "betType": bet_type,
            "selection": selection or "",
            "odds": odds or 0
        }
        legs.append(leg)
    
    # 计算置信度（基于识别到的字段数量）
    total_fields = 7  # 总字段数
    identified_fields = sum([
        bool(home_team),
        bool(away_team),
        bool(league),
        bool(match_date),
        bool(bet_type),
        bool(selection),
        bool(odds)
    ])
    
    confidence = identified_fields / total_fields
    
    result = {
        "legs": legs,
        "stake": stake or 0,
        "confidence": round(confidence, 4)
    }
    
    # 如果有多场赛事（串关），默认使用2串1
    if len(legs) > 1:
        result["parlayType"] = f"{len(legs)}_1"
    
    logger.info(f"投注信息解析完成，识别字段: {identified_fields}/{total_fields}, 置信度: {confidence:.2f}")
    
    return result


def parse_bet_image_result(ocr_result: Dict[str, Any]) -> Dict[str, Any]:
    """解析OCR识别结果，提取投注信息（API层调用的入口函数）
    
    Args:
        ocr_result: OCR识别结果，格式：
            {
                "success": True,
                "text": "完整文本",
                "details": [OCR详细结果],
                "confidence": 0.92
            }
            
    Returns:
        {
            "success": True,
            "data": {
                "legs": [...],
                "stake": 100,
                "confidence": 0.85
            },
            "raw_text": "OCR识别的原始文本",
            "ocr_confidence": 0.92
        }
    """
    if not ocr_result.get("success"):
        return {
            "success": False,
            "error": ocr_result.get("error", "OCR识别失败"),
            "data": None,
            "raw_text": ""
        }
    
    text = ocr_result.get("text", "")
    ocr_details = ocr_result.get("details", [])
    ocr_confidence = ocr_result.get("confidence", 0.0)
    
    logger.info(f"OCR识别的原始文本: {text}")
    
    if not text:
        return {
            "success": False,
            "error": "未识别到任何文字",
            "data": None,
            "raw_text": ""
        }
    
    # 解析投注信息
    try:
        bet_info = parse_bet_info(text, ocr_details)
        
        # 如果没有识别到任何赛事信息，返回失败
        if not bet_info["legs"]:
            return {
                "success": False,
                "error": "未能识别到有效的投注信息，请检查图片内容",
                "data": bet_info,
                "raw_text": text,
                "ocr_confidence": ocr_confidence
            }
        
        return {
            "success": True,
            "data": bet_info,
            "raw_text": text,
            "ocr_confidence": ocr_confidence
        }
        
    except Exception as e:
        logger.error(f"解析投注信息失败: {e}", exc_info=True)
        return {
            "success": False,
            "error": f"解析失败: {str(e)}",
            "data": None,
            "raw_text": text,
            "ocr_confidence": ocr_confidence
        }
