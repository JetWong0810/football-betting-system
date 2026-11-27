"""去水概率偏差修正、倾向结构化提取的测试。python3 test_chat_bias.py"""
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
from match_chat.context import BASE_RATE_TEXT, devig_text, split_sections  # noqa: E402
from match_chat.service import extract_verdict  # noqa: E402


def test_devig_is_relative_to_norm():
    # 科莫(主)让1.75, 主水0.98/客水0.88: 上盘(科莫)去水 48.7%, 与常态49.3%只差0.6pp -> 不提供方向信息
    t = devig_text(1.75, "科莫", "AEK", 0.98, 0.88)
    assert "上盘(科莫)定价概率 48.7%" in t and "在常态范围内" in t and "站下盘" not in t, t
    # 主受让: 上盘是客队
    t = devig_text(-1.0, "甲", "乙", 0.80, 1.00)
    assert "上盘(乙)" in t, t
    # 明显偏离常态
    t = devig_text(0.5, "甲", "乙", 0.80, 1.05)
    assert "高于常态" in t, t
    # 平手盘无上下盘常态
    assert "不单独作为方向依据" in devig_text(0, "甲", "乙", 0.9, 0.95)
    assert devig_text(0.5, "甲", "乙", None, 0.9) == ""


def test_base_rate_section_kept():
    text = "【比赛】\nx\n【盘口读法】a\n" + BASE_RATE_TEXT + "\n【水位参考·亚盘】b\n【历史同赔 F6】c"
    odds = split_sections(text)["odds"]
    assert "赢盘基准" in odds and "水位参考" in odds


def test_prompt_has_graded_leans_and_no_price_veto():
    from match_chat.service import SYSTEM_TMPL
    assert "微弱倾向" in SYSTEM_TMPL and "中等倾向" in SYSTEM_TMPL and "较明显倾向" in SYSTEM_TMPL
    assert "不要用\"价格上不下手\"当结论" in SYSTEM_TMPL and "买什么盘口水位合适" not in SYSTEM_TMPL
    from match_chat.service import SUMMARY_NOTE
    assert "买什么盘口水位合适" not in SUMMARY_NOTE and "证据不足一律写不确定" not in SUMMARY_NOTE
    assert "至少两类互相独立的证据" in SYSTEM_TMPL and "只有一类证据、证据互相矛盾" not in SYSTEM_TMPL


def test_ou_prompt_guards_against_double_counting_line_moves():
    from match_chat.service import SYSTEM_TMPL
    assert "已经体现在当前的 μ 里" in SYSTEM_TMPL and "不要用\"盘口已定价\"当作不给倾向的理由" in SYSTEM_TMPL


def test_motivation_news_guidance():
    from match_chat.service import NO_WEB_OU_NOTE, WEB_ON_NOTE
    assert "战意与赛前情报" in WEB_ON_NOTE and "主帅或球队官方原话" in WEB_ON_NOTE and "没有回测,只能给方向" in WEB_ON_NOTE
    assert "缺少赛前新闻和主帅发言" in NO_WEB_OU_NOTE


def test_news_and_article_intel_not_downgraded():
    from match_chat.service import SYSTEM_TMPL
    # 新闻/发言/文章情报被明确列为新信息, 且有"新闻时间 vs 盘口变动时间"的吸收判断
    assert "联网查到的主帅发言和内部消息" in SYSTEM_TMPL and "关联文章里已证实或能交叉验证的事实" in SYSTEM_TMPL
    assert "新闻发布时间对照盘口最近一次变动时间" in SYSTEM_TMPL and "尚未被定价的信息,这时它的分量最大" in SYSTEM_TMPL
    # 新闻情报按事实计类, 可以撑起中等强度; 文章事实与观点分开
    assert "新闻情报内部按\"事实\"而不是按渠道数" in SYSTEM_TMPL and "可以和其他因素一起撑起\"中等\"强度" in SYSTEM_TMPL
    assert "事实(伤停、停赛、首发消息" in SYSTEM_TMPL and "观点" in SYSTEM_TMPL
    assert "④对照【历史信号】" in SYSTEM_TMPL and "④③" not in SYSTEM_TMPL


def test_extract_verdict():
    body, v = extract_verdict("正文\n[[NEXT]] 问题一 || 问题二\n[[V]] ah=下盘; ou=不确定")
    assert v == {"ah": "下盘", "ou": "不确定"} and "[[V]]" not in body and "[[NEXT]]" in body, (body, v)
    body, v = extract_verdict("正文\n[[V]] ah=上盘/微弱; ou=不确定")
    assert v == {"ah": "上盘", "ou": "不确定", "ah_s": "微弱"} and "[[V]]" not in body, (body, v)
    body, v = extract_verdict("正文\n[[V]] ah=下盘/中等; ou=大球/较明显")
    assert v == {"ah": "下盘", "ou": "大球", "ah_s": "中等", "ou_s": "较明显"}, v
    body, v = extract_verdict("x\n[[V]] ah=上盘/随便; ou=无")           # 非法强度忽略, 方向仍保留
    assert v == {"ah": "上盘", "ou": "无"}, v
    body, v = extract_verdict("没有倾向的回复")
    assert v is None and body == "没有倾向的回复"
    body, v = extract_verdict("x\n[[V]] 格式不对")
    assert v is None and "[[V]]" not in body


if __name__ == "__main__":
    for n, f in list(globals().items()):
        if n.startswith("test_"):
            f()
            print("ok", n)
