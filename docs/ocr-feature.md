# OCR 图片识别功能

## 功能概述

识别投注截图中的关键信息（球队、联赛、赔率、金额等），自动生成投注记录。

## 技术方案

- **OCR 引擎**: RapidOCR (rapidocr_onnxruntime) — PaddleOCR 模型的 ONNX 推理版本
- **图像处理**: OpenCV + Pillow
- **投注解析**: 正则表达式 + 规则匹配 (bet_parser.py)

优势（相比原 PaddleOCR 方案）：
- 安装体积 ~80MB vs ~1.5GB+
- 无需 paddlepaddle 框架
- 纯 pip install，Docker 友好
- 识别效果一致（使用相同模型）

## 架构

```
前端上传图片 (Base64)
    ↓
POST /api/ocr/parse-bet-image
    ↓
ocr_service.py (RapidOCR)
    ↓
bet_parser.py (结构化解析)
    ↓
返回投注信息 JSON
```

## API

```bash
# 检查 OCR 状态
curl http://localhost:7001/api/ocr/status

# 识别投注图片（需认证）
curl -X POST http://localhost:7001/api/ocr/parse-bet-image \
  -H "Authorization: Bearer TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"image_base64": "..."}'
```

## 安装

```bash
cd api-service
pip install rapidocr_onnxruntime opencv-python Pillow
```

首次调用会自动下载 ONNX 模型（~10MB），后续调用无需网络。

## 测试

```bash
cd api-service
python3 test_ocr.py
```

## 关键文件

| 文件 | 说明 |
|------|------|
| api-service/ocr_service.py | OCR 引擎封装 |
| api-service/bet_parser.py | 投注信息解析 |
| api-service/test_ocr.py | 功能测试 |
| frontend/src/pages/record/ocr-upload.vue | 前端上传页面 |
