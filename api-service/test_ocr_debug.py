"""测试 OCR 识别并打印详细结果"""
import sys
sys.path.insert(0, '/Users/jetwong/Projects/football-betting-system/api-service')

from ocr_service import recognize_image
from bet_parser import parse_bet_image_result
import json

# 从命令行获取 base64 字符串
if len(sys.argv) > 1:
    base64_str = sys.argv[1]
else:
    # 默认测试图片（白色背景）
    base64_str = "iVBORw0KGgoAAAANSUhEUgAAAMgAAABQCAIAAADTD63nAAAA6ElEQVR4nO3SwQ3AIBDAsNL9dz6WIEJC9gR5ZM3MB6f9twN4k7FIGIuEsUgYi4SxSBiLhLFIGIuEsUgYi4SxSBiLhLFIGIuEsUgYi4SxSBiLhLFIGIuEsUgYi4SxSBiLhLFIGIuEsUgYi4SxSBiLhLFIGIuEsUgYi4SxSBiLhLFIGIuEsUgYi4SxSBiLhLFIGIuEsUgYi4SxSBiLhLFIGIuEsUgYi4SxSBiLhLFIGIuEsUgYi4SxSBiLhLFIGIuEsUgYi4SxSBiLxAbHugOdXmUxkQAAAABJRU5ErkJggg=="

print("=" * 80)
print("OCR 识别测试")
print("=" * 80)

# 1. OCR 识别
print("\n步骤 1: OCR 识别图片...")
ocr_result = recognize_image(base64_str, source_type="base64")

print(f"\nOCR 识别成功: {ocr_result['success']}")
print(f"置信度: {ocr_result.get('confidence', 0)}")
print(f"\n识别的文本:\n{ocr_result.get('text', '')}")
print(f"\n详细结果 ({len(ocr_result.get('details', []))} 行):")
for i, detail in enumerate(ocr_result.get('details', [])[:10], 1):  # 只显示前10行
    print(f"  {i}. {detail['text']} (置信度: {detail['confidence']:.2f})")

# 2. 解析投注信息
print("\n" + "=" * 80)
print("步骤 2: 解析投注信息...")
parse_result = parse_bet_image_result(ocr_result)

print(f"\n解析成功: {parse_result['success']}")
if parse_result['success']:
    print(f"\n投注信息:")
    print(json.dumps(parse_result.get('data', {}), indent=2, ensure_ascii=False))
else:
    print(f"\n错误: {parse_result.get('error', '未知错误')}")

print("\n" + "=" * 80)
