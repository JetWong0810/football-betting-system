"""裁判块的测试(不联网不连库, 用替身代替缓存读取)。python3 test_af_referee.py"""
import os
import sys
from datetime import datetime

sys.path.insert(0, os.path.dirname(__file__))
from api_football import referee  # noqa: E402
from match_chat.service import NO_WEB_OU_NOTE, WEB_ON_NOTE, wanted_sections  # noqa: E402


def test_clean_name():
    assert referee.clean_name("Felix Zwayer, Germany") == "Felix Zwayer"
    assert referee.clean_name("Andrew Madley") == "Andrew Madley"
    assert referee.clean_name("  ") is None and referee.clean_name(None) is None
    assert referee.clean_name("Robert Madley, England") == "Robert Madley"


def test_render_states():
    saved = referee.load_cached
    try:
        referee.load_cached = lambda mid: None
        t = referee.render("m", "甲", "乙")
        assert "还没有查询" in t and "不要凭印象写裁判" in t and "可靠性提醒" in t
        referee.load_cached = lambda mid: {"referee": None, "fetchedAt": datetime(2026, 11, 27, 6, 0)}
        t = referee.render("m", "甲", "乙")
        assert "尚未公布" in t and "裁判未公布" in t
        referee.load_cached = lambda mid: {"referee": "Andrew Madley", "fetchedAt": datetime(2026, 11, 27, 6, 0)}
        t = referee.render("m", "甲", "乙")
        assert "Andrew Madley" in t and "联网查这位裁判" in t
        # 可靠性提醒必须带上我们检验出的结论, 防止对着小样本编故事
        assert "点球判罚、总进球基本没有个人稳定性" in t and "75%" in t and "不得暗示裁判受贿或操纵比赛" in t and "没有回测支持" in t
    finally:
        referee.load_cached = saved


def test_trigger_words():
    assert "ref" in wanted_sections("请关联本场裁判信息,分析他的风格")
    assert "ref" in wanted_sections("请关联本场主裁的判罚倾向")
    assert "ref" not in wanted_sections("裁判一般怎么选")                 # 没有关联意图不触发
    assert "ref" in wanted_sections("请关联本场全部数据")
    assert "ref" not in wanted_sections("请关联本场大小球相关数据")        # 大小球打包不含裁判(保持上下文精简)


def test_web_note_has_referee_guidance():
    assert "裁判风格与倾向" in WEB_ON_NOTE and "不得暗示裁判受贿、操纵比赛或有意偏袒" in WEB_ON_NOTE
    assert "没有证据" in WEB_ON_NOTE and "样本" in WEB_ON_NOTE and "WhoScored" in WEB_ON_NOTE
    assert NO_WEB_OU_NOTE                                                  # 原有的无联网提示不受影响


if __name__ == "__main__":
    for k, f in list(globals().items()):
        if k.startswith("test_"):
            f()
            print("ok", k)
