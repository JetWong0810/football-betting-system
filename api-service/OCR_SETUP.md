# OCR 功能配置说明

## 当前配置（已修复）

### 环境信息
- **PaddleOCR 版本**: 3.3.2
- **Python 版本**: 3.9
- **平台**: macOS
- **推理方式**: CPU

### 最终可用配置

```python
from paddleocr import PaddleOCR

ocr = PaddleOCR(
    use_angle_cls=False,  # 禁用文本方向分类，提升速度
    lang='ch'              # 中文识别
)
```

**重要说明**：
- PaddleOCR 3.x 版本参数与 2.x 版本不兼容
- 不要使用 `use_gpu`、`use_mp`、`show_log`、`enable_mkldnn` 等参数（会报错）
- 保持最简配置即可正常工作

## 已解决的问题

### 问题 1: OCR 模块导入失败 - `No module named 'cv2'`

**原因**: 
- `uvicorn` 命令使用的是 Python 3.8 环境
- OCR 依赖安装在 Python 3.9 环境

**解决方案**:
```bash
# 启动脚本改为使用 python3 -m uvicorn
python3 -m uvicorn main:app --host 0.0.0.0 --port 7001
```

### 问题 2: PaddleOCR 初始化失败 - `Unknown argument: use_mp`

**原因**: PaddleOCR 3.x 不支持 `use_mp` 参数

**解决方案**: 移除不兼容参数

### 问题 3: PaddleOCR 初始化失败 - `Unknown argument: show_log`

**原因**: PaddleOCR 3.x 不支持 `show_log` 参数

**解决方案**: 移除不兼容参数

### 问题 4: PaddleOCR 初始化失败 - `Unknown argument: use_gpu`

**原因**: PaddleOCR 3.x 的 GPU 参数格式已变更

**解决方案**: 完全移除，使用默认 CPU 推理

## 性能优化

### 已实施的优化

1. **禁用文本方向分类** (`use_angle_cls=False`)
   - 效果：减少约 30% 处理时间
   - 适用场景：正常拍摄的截图（非旋转图片）

2. **关闭图片预处理** (`preprocess=False`)
   - 移除耗时的降噪和增强操作
   - 效果：节省 5-10 秒
   - PaddleOCR 本身已足够强大，无需额外预处理

3. **优化图片尺寸**
   - 最大尺寸限制：1600 像素
   - 使用更快的 BILINEAR 缩放算法

### 预期性能

- **优化前**: 40+ 秒/图
- **优化后**: 10-15 秒/图（取决于图片大小和复杂度）

**注意**: 
- macOS 不支持 GPU 加速，性能受 CPU 限制
- 首次识别会下载模型（~100MB），耗时较长
- 后续识别会使用缓存模型，速度正常

## 测试 OCR 功能

### 1. 检查服务状态

```bash
curl http://localhost:7001/api/ocr/status
```

预期返回：
```json
{"available":true,"message":"OCR服务正常"}
```

### 2. 测试图片识别

需要先登录获取 token：

```bash
# 登录
TOKEN=$(curl -s -X POST http://localhost:7001/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username":"your_username","password":"your_password"}' \
  | jq -r '.access_token')

# 测试 OCR（需要 base64 编码的图片）
curl -X POST http://localhost:7001/api/ocr/parse-bet-image \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"image_base64":"YOUR_BASE64_IMAGE_DATA"}'
```

### 3. 查看日志

```bash
# 实时查看 OCR 识别日志
tail -f logs/api-service.log | grep "OCR"

# 查看错误日志
tail -f logs/api-service.log | grep -i "error\|exception"
```

## 已知限制

1. **首次启动慢**
   - PaddleOCR 首次初始化会下载模型（~100MB）
   - 模型缓存在 `~/.paddlex/official_models/`
   - 建议首次启动后等待 1-2 分钟

2. **CPU 性能限制**
   - macOS 不支持 GPU 加速
   - 识别速度取决于 CPU 性能
   - 高分辨率图片识别较慢

3. **内存占用**
   - PaddleOCR 模型较大（~200MB 内存）
   - 首次调用会加载模型到内存
   - 后续调用复用已加载的模型

## 进一步优化建议

如需更快的识别速度，考虑以下方案：

### 方案 1: 使用轻量级模型

手动下载并配置更小的模型：

```python
PaddleOCR(
    det_model_dir='path/to/mobile_det_model',
    rec_model_dir='path/to/mobile_rec_model'
)
```

### 方案 2: 使用云服务 OCR

集成第三方 OCR API（速度 1-2 秒）：

- **百度 OCR**: https://ai.baidu.com/tech/ocr
- **腾讯云 OCR**: https://cloud.tencent.com/product/ocr
- **阿里云 OCR**: https://www.aliyun.com/product/ocr

优点：速度快、准确率高  
缺点：需要付费、依赖网络

### 方案 3: 部署在 GPU 服务器

在 Linux 服务器上启用 GPU 加速：

```python
PaddleOCR(
    use_angle_cls=False,
    lang='ch'
    # PaddleOCR 会自动检测并使用 GPU
)
```

需要：
- NVIDIA GPU
- CUDA 和 cuDNN
- paddlepaddle-gpu 包

性能提升：5-10x

## 维护建议

1. **定期清理模型缓存**（如果磁盘空间紧张）
   ```bash
   rm -rf ~/.paddlex/official_models/
   ```

2. **监控识别性能**
   - 关注日志中的识别时间
   - 检查识别准确率

3. **升级 PaddleOCR**（谨慎）
   ```bash
   pip3 install -U paddleocr
   ```
   注意：升级后可能需要重新调整参数

## 故障排查

### OCR 服务不可用

1. 检查依赖是否安装：
   ```bash
   python3 -c "import cv2, PIL, paddleocr; print('All dependencies OK')"
   ```

2. 检查 Python 环境一致性：
   ```bash
   which python3
   python3 -c "import sys; print(sys.executable)"
   ```

3. 重启服务：
   ```bash
   ./start-local.sh --restart
   ```

### 识别速度太慢

1. 检查图片尺寸是否过大
2. 确认是否是首次识别（需要下载模型）
3. 查看 CPU 使用率是否正常

### 识别准确率低

1. 确保图片清晰、对比度高
2. 尝试启用预处理（修改代码）：
   ```python
   extract_text_from_image(image, preprocess=True, fast_mode=False)
   ```

## 文件说明

- `ocr_service.py`: OCR 核心服务（图片识别）
- `bet_parser.py`: 投注信息解析（OCR 结果 → 结构化数据）
- `main.py`: API 入口，包含 OCR 相关路由

## API 端点

- `GET /api/ocr/status`: 检查 OCR 服务状态
- `POST /api/ocr/parse-bet-image`: 识别投注图片（需要认证）

## 相关文档

- PaddleOCR 官方文档: https://github.com/PaddlePaddle/PaddleOCR
- 项目部署说明: `../WARP.md`
- 本地启动说明: `../START_LOCAL_README.md`
