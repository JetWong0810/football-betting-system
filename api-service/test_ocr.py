"""OCR功能测试脚本

用于测试OCR识别和投注信息解析功能
"""
import logging

# 设置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

def test_ocr_basic():
    """测试基础OCR功能"""
    print("\n" + "="*60)
    print("测试1: 基础OCR功能")
    print("="*60)
    
    try:
        from ocr_service import get_ocr_instance
        
        print("✓ OCR模块导入成功")
        
        # 初始化OCR实例
        ocr = get_ocr_instance()
        print("✓ PaddleOCR初始化成功")
        
        return True
    except Exception as e:
        print(f"✗ OCR初始化失败: {e}")
        return False


def test_bet_parser():
    """测试投注信息解析功能"""
    print("\n" + "="*60)
    print("测试2: 投注信息解析功能")
    print("="*60)
    
    try:
        from bet_parser import (
            extract_teams,
            extract_league,
            extract_date,
            extract_bet_type,
            extract_selection_and_odds,
            extract_stake
        )
        
        # 测试文本
        test_text = "英超 曼联 vs 利物浦 2025-11-30 让球 +0.5 赔率: 1.85 投注: 100元"
        
        print(f"\n测试文本: {test_text}\n")
        
        # 提取球队
        home_team, away_team = extract_teams(test_text)
        print(f"主队: {home_team}, 客队: {away_team}")
        
        # 提取联赛
        league = extract_league(test_text)
        print(f"联赛: {league}")
        
        # 提取日期
        date = extract_date(test_text)
        print(f"日期: {date}")
        
        # 提取投注类型
        bet_type = extract_bet_type(test_text)
        print(f"投注类型: {bet_type}")
        
        # 提取投注方向和赔率
        selection, odds = extract_selection_and_odds(test_text, bet_type)
        print(f"投注方向: {selection}, 赔率: {odds}")
        
        # 提取投注金额
        stake = extract_stake(test_text)
        print(f"投注金额: {stake}")
        
        # 验证结果
        success = all([
            home_team == "曼联",
            away_team == "利物浦",
            league == "英超",
            date == "2025-11-30",
            bet_type == "让球",
            selection == "+0.5",
            odds == 1.85,
            stake == 100
        ])
        
        if success:
            print("\n✓ 所有解析结果正确")
        else:
            print("\n✗ 部分解析结果不正确")
        
        return success
        
    except Exception as e:
        print(f"✗ 解析功能测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_full_parse():
    """测试完整的解析流程"""
    print("\n" + "="*60)
    print("测试3: 完整解析流程")
    print("="*60)
    
    try:
        from bet_parser import parse_bet_info
        
        test_texts = [
            {
                "text": "英超 曼联 vs 利物浦 2025-11-30 胜平负 主胜 赔率: 2.10 投注100元",
                "expected": {
                    "homeTeam": "曼联",
                    "awayTeam": "利物浦",
                    "league": "英超",
                    "betType": "胜平负",
                    "selection": "主胜"
                }
            },
            {
                "text": "西甲 皇马-巴萨 让球 +1 @1.95 下注200",
                "expected": {
                    "homeTeam": "皇马",
                    "awayTeam": "巴萨",
                    "league": "西甲",
                    "betType": "让球",
                    "selection": "+1"
                }
            },
            {
                "text": "意甲 尤文对米兰 大小球 大2.5 赔率1.88 金额:50",
                "expected": {
                    "homeTeam": "尤文",
                    "awayTeam": "米兰",
                    "league": "意甲",
                    "betType": "大小球",
                    "selection": "大2.5"
                }
            }
        ]
        
        all_passed = True
        
        for i, test_case in enumerate(test_texts, 1):
            print(f"\n测试用例 {i}:")
            print(f"文本: {test_case['text']}")
            
            result = parse_bet_info(test_case['text'])
            
            if result['legs']:
                leg = result['legs'][0]
                print(f"解析结果: {leg}")
                
                # 验证关键字段
                expected = test_case['expected']
                passed = all([
                    leg.get('homeTeam') == expected.get('homeTeam'),
                    leg.get('awayTeam') == expected.get('awayTeam'),
                    leg.get('league') == expected.get('league'),
                    leg.get('betType') == expected.get('betType')
                ])
                
                if passed:
                    print(f"✓ 测试用例 {i} 通过")
                else:
                    print(f"✗ 测试用例 {i} 失败")
                    all_passed = False
            else:
                print(f"✗ 测试用例 {i} 未识别到赛事信息")
                all_passed = False
        
        return all_passed
        
    except Exception as e:
        print(f"✗ 完整解析流程测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False


def main():
    """运行所有测试"""
    print("\n" + "="*60)
    print("OCR功能测试")
    print("="*60)
    
    results = []
    
    # 测试1: 基础OCR功能
    results.append(("基础OCR功能", test_ocr_basic()))
    
    # 测试2: 投注信息解析
    results.append(("投注信息解析功能", test_bet_parser()))
    
    # 测试3: 完整解析流程
    results.append(("完整解析流程", test_full_parse()))
    
    # 总结
    print("\n" + "="*60)
    print("测试结果汇总")
    print("="*60)
    
    for name, passed in results:
        status = "✓ 通过" if passed else "✗ 失败"
        print(f"{name}: {status}")
    
    all_passed = all(result[1] for result in results)
    
    print("\n" + "="*60)
    if all_passed:
        print("✓ 所有测试通过！")
    else:
        print("✗ 部分测试失败，请检查错误信息")
    print("="*60 + "\n")
    
    return all_passed


if __name__ == "__main__":
    success = main()
    exit(0 if success else 1)
