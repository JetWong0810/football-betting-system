#!/bin/bash
# OCR 测试脚本
# 使用方法: ./test_image_ocr.sh <图片路径>

if [ -z "$1" ]; then
    echo "使用方法: $0 <图片路径>"
    echo "示例: $0 ~/Downloads/bet.jpg"
    exit 1
fi

IMAGE_PATH="$1"

if [ ! -f "$IMAGE_PATH" ]; then
    echo "错误: 文件不存在 - $IMAGE_PATH"
    exit 1
fi

echo "========================================"
echo "OCR 图片识别测试"
echo "========================================"
echo "图片路径: $IMAGE_PATH"
echo ""

# 将图片转换为 base64
echo "步骤 1: 转换图片为 base64..."
BASE64_DATA=$(base64 -i "$IMAGE_PATH" | tr -d '\n')
echo "Base64 长度: ${#BASE64_DATA} 字符"
echo ""

# 创建临时 JSON 文件
TMP_JSON=$(mktemp)
cat > "$TMP_JSON" <<EOF
{
  "image_base64": "$BASE64_DATA"
}
EOF

echo "步骤 2: 调用 OCR API..."
echo ""

# 调用 API（需要先登录获取 token）
# 这里使用一个测试 token，实际使用时需要先登录
curl -X POST http://localhost:7001/api/ocr/parse-bet-image \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer test-token-replace-me" \
  -d @"$TMP_JSON" \
  | python3 -m json.tool

# 清理临时文件
rm "$TMP_JSON"

echo ""
echo "========================================"
echo "提示: 如果返回 401，请先登录获取 token"
echo "========================================"
