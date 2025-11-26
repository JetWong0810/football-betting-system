# OCR 图片识别功能说明文档

## 功能概述

本系统集成了 OCR（光学字符识别）功能，可以自动识别投注截图中的关键信息，包括：
- 球队名称（主队 vs 客队）
- 联赛信息
- 比赛日期和时间
- 投注类型（胜平负、让球、大小球等）
- 投注方向和赔率
- 投注金额

识别后的信息可直接保存为投注记录，大大提升录入效率。

## 技术架构

### 核心组件

1. **OCR 引擎**: PaddleOCR 3.3.2
   - 使用 PaddlePaddle 深度学习框架
   - 支持中文识别
   - CPU 推理，无需 GPU

2. **图像处理**: OpenCV 4.12.0
   - 图片预处理（对比度增强、降噪）
   - 格式转换

3. **投注信息解析**: 正则表达式 + 规则匹配
   - 提取球队、联赛、赔率等结构化信息
   - 支持多种投注格式

### 系统架构

```
前端 (UniApp H5/小程序)
    ↓ 上传图片 (Base64)
API 服务 (FastAPI)
    ↓ OCR 识别
ocr_service.py (PaddleOCR)
    ↓ 文本提取
bet_parser.py (信息解析)
    ↓ 结构化数据
数据库 (MySQL)
```

## 依赖安装

### 后端依赖

在 `api-service/requirements.txt` 中已包含以下 OCR 相关依赖：

```txt
# OCR dependencies
paddleocr>=2.7.0
paddlepaddle>=2.6.0
opencv-python-headless>=4.8.1
Pillow>=10.1.0
```

### 安装命令

```bash
cd api-service
pip3 install -r requirements.txt

# 或单独安装
pip3 install paddleocr paddlepaddle opencv-python-headless Pillow
```

**注意**：
- 首次运行会自动下载 PaddleOCR 模型（约 200MB）
- 模型缓存位置：`~/.paddlex/official_models/`
- macOS 建议使用 `opencv-python-headless`（无 GUI 依赖）

## 服务启动

### 方式一：开发模式（推荐用于本地开发）

```bash
cd /path/to/football-betting-system/api-service

# 方法 1: 使用 main.py
python3 main.py

# 方法 2: 使用 uvicorn（支持热重载）
uvicorn main:app --host 0.0.0.0 --port 7001 --reload
```

### 方式二：后台运行（推荐用于测试）

```bash
cd /path/to/football-betting-system/api-service

# 后台运行并记录日志
nohup python3 main.py > /tmp/api-service.log 2>&1 &

# 或使用 uvicorn
nohup uvicorn main:app --host 0.0.0.0 --port 7001 --reload > /tmp/api-service.log 2>&1 &

# 查看日志
tail -f /tmp/api-service.log
```

### 方式三：生产环境部署

生产环境使用 systemd 管理（已配置在 `guiyun` 服务器）：

```bash
# 启动服务
sudo systemctl start football-betting-api

# 停止服务
sudo systemctl stop football-betting-api

# 重启服务
sudo systemctl restart football-betting-api

# 查看状态
sudo systemctl status football-betting-api

# 查看日志
sudo journalctl -u football-betting-api -f
```

### 前端服务启动

```bash
cd /path/to/football-betting-system/frontend

# H5 开发模式
npm run dev:h5
# 访问: http://localhost:5173

# 小程序开发模式
npm run dev:mp-weixin

# 后台运行 H5（用于测试）
nohup npm run dev:h5 > /tmp/frontend.log 2>&1 &
```

## 核心代码说明

### 1. OCR 服务模块 (`ocr_service.py`)

**关键函数**：

```python
def get_ocr_instance():
    """获取 OCR 实例（单例模式）"""
    # 初始化 PaddleOCR
    # use_angle_cls=False: 禁用角度分类（避免参数兼容问题）
    # lang='ch': 中文识别
    
def recognize_image(image_source: str, source_type: str = "base64"):
    """识别图片中的文字（统一入口）"""
    # 1. 解析 base64/文件
    # 2. 图片预处理（可选）
    # 3. OCR 识别
    # 4. 返回文本和置信度

def extract_text_from_image(image: Image.Image, preprocess: bool = True):
    """从图片中提取文字"""
    # 关键：兼容 PaddleOCR 3.x 新旧两种返回格式
    # 新格式：字典 {'rec_texts': [...], 'rec_scores': [...]}
    # 旧格式：列表 [[box, (text, confidence)]]
```

**PaddleOCR 3.x 兼容性处理**：

```python
# PaddleOCR 3.3.2 返回新格式：字典列表
if isinstance(first_item, dict):
    rec_texts = first_item.get('rec_texts', [])
    rec_scores = first_item.get('rec_scores', [])
    rec_polys = first_item.get('rec_polys', [])
    
# 旧版本格式（兼容处理）
elif isinstance(first_item, list):
    for line in result[0]:
        box = line[0]
        text, confidence = line[1]
```

### 2. 投注信息解析模块 (`bet_parser.py`)

**关键函数**：

```python
def extract_teams(text: str) -> Tuple[Optional[str], Optional[str]]:
    """提取主队和客队"""
    # 支持格式: "曼联 vs 利物浦", "曼联-利物浦", "曼联对利物浦"

def extract_league(text: str) -> Optional[str]:
    """提取联赛名称"""
    # 匹配常见联赛关键词：英超、西甲、意甲等

def extract_bet_type(text: str) -> Optional[str]:
    """提取投注类型"""
    # 识别：胜平负、让球、大小球

def extract_selection_and_odds(text: str, bet_type: str):
    """提取投注方向和赔率"""
    # 胜平负：主胜/平局/主负
    # 让球：+0.5, -1 等
    # 大小球：大2.5, 小3 等

def extract_stake(text: str) -> Optional[float]:
    """提取投注金额"""
    # 识别：100元、投注:100、金额:100

def parse_bet_image_result(ocr_result: Dict) -> Dict:
    """解析 OCR 结果，提取投注信息（API 入口）"""
    # 综合以上函数，返回完整的投注信息
```

### 3. API 接口 (`main.py`)

```python
@app.post("/api/ocr/parse-bet-image")
def parse_bet_image(req: OcrParseImageRequest, user_id: int = Depends(require_auth)):
    """OCR 识别投注图片"""
    # 1. 检查 OCR 服务可用性
    # 2. 调用 recognize_image 识别图片
    # 3. 调用 parse_bet_image_result 解析投注信息
    # 4. 返回结构化数据

@app.get("/api/ocr/status")
def ocr_status():
    """检查 OCR 服务状态"""
    return {"available": OCR_AVAILABLE}
```

### 4. 前端实现 (`ocr-upload.vue`)

**关键功能**：

```javascript
// 选择图片
const chooseImage = () => {
  uni.chooseImage({...})
  // H5: 使用 fetch + FileReader 读取 base64
  // 小程序: 使用 FileSystemManager 读取
}

// 识别图片
const recognizeImage = async () => {
  await request({
    url: '/api/ocr/parse-bet-image',
    method: 'POST',
    timeout: 60000,  // 60秒超时（首次初始化需要时间）
    data: { image_base64: imageBase64.value }
  })
}

// 保存为投注记录
const saveBet = async () => {
  await request({
    url: '/api/bets',
    method: 'POST',
    data: betRecord
  })
}
```

## 使用方法

### 前端操作流程

1. **登录系统**
   - H5: http://localhost:5173/#/pages/auth/login
   - 默认账号: admin / admin123

2. **进入识别页面**
   - 方式 1: 投注记录页面 → 点击右上角 📷 识别按钮
   - 方式 2: 直接访问 http://localhost:5173/#/pages/record/ocr-upload

3. **上传图片**
   - 点击上传区域选择图片
   - 或拖拽图片到上传区域（H5）
   - 支持 JPG、PNG 格式

4. **开始识别**
   - 点击"开始识别"按钮
   - 首次识别约需 20-30 秒（加载模型）
   - 后续识别 3-5 秒

5. **查看结果**
   - 识别文本：显示 OCR 提取的原始文字
   - 投注信息：显示解析后的结构化数据
   - 可手动调整后保存

6. **保存记录**
   - 点击"保存为投注记录"
   - 自动跳转回投注记录列表

### API 调用示例

**1. 检查 OCR 服务状态**

```bash
curl http://localhost:7001/api/ocr/status
```

响应：
```json
{
  "available": true,
  "message": "OCR服务正常"
}
```

**2. 识别投注图片**

```bash
# 需要先登录获取 token
curl -X POST http://localhost:7001/api/ocr/parse-bet-image \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -d '{
    "image_base64": "iVBORw0KGgo..."
  }'
```

响应示例：
```json
{
  "success": true,
  "data": {
    "legs": [
      {
        "homeTeam": "杰巴布拉瓦",
        "awayTeam": "雷昂内斯",
        "league": "墨西哥甲级联赛",
        "matchDate": "2025-11-17",
        "betType": "大小球",
        "selection": "大6",
        "odds": 2.14
      }
    ],
    "stake": 200.63,
    "confidence": 0.85
  },
  "raw_text": "杰巴布拉瓦 VS 雷昂内斯 比赛时间: 2025-11-17 10:00:00...",
  "ocr_confidence": 0.92
}
```

## 测试工具

### 1. 单元测试

```bash
cd api-service

# 运行 OCR 功能测试
python3 test_ocr.py
```

测试内容：
- ✓ OCR 基础功能
- ✓ 投注信息解析
- ✓ 完整解析流程

### 2. 调试脚本

```bash
# 测试指定图片
python3 test_ocr_debug.py [BASE64_STRING]

# 使用图片文件测试（需要先添加执行权限）
chmod +x test_image_ocr.sh
./test_image_ocr.sh /path/to/image.jpg
```

### 3. 查看日志

```bash
# 实时查看 API 服务日志
tail -f /tmp/api-service.log

# 查看 OCR 识别日志
tail -f /tmp/api-service.log | grep -E "(OCR|识别|parse-bet)"

# 查看前端日志
tail -f /tmp/frontend.log
```

## 常见问题

### 1. OCR 服务不可用

**问题**: `/api/ocr/status` 返回 `available: false`

**解决方法**:
```bash
# 检查依赖是否安装
pip3 list | grep -E "(paddleocr|paddlepaddle|opencv)"

# 重新安装
pip3 install paddleocr paddlepaddle opencv-python-headless Pillow

# 重启服务
```

### 2. 识别超时

**问题**: 前端提示 "request:fail timeout"

**原因**: 首次加载模型需要 20-30 秒

**解决方法**:
- 前端已设置 60 秒超时
- 耐心等待首次识别完成
- 后续识别会快很多

### 3. 识别结果为空

**问题**: 返回 "未识别到任何文字"

**可能原因**:
- 图片质量太差（模糊、光线不足）
- 图片对比度低
- 文字区域太小

**解决方法**:
- 使用清晰的截图
- 确保文字清晰可见
- 避免图片旋转或倾斜

### 4. 无法解析投注信息

**问题**: OCR 识别成功但 "未能识别到有效的投注信息"

**原因**: 文本格式不符合解析规则

**解决方法**:
- 确保图片包含关键信息：球队、联赛、赔率、金额
- 参考测试图片格式
- 手动调整识别结果后保存

### 5. 端口占用

**问题**: 启动失败 "Address already in use"

**解决方法**:
```bash
# 查找占用端口的进程
lsof -i :7001

# 停止进程
kill -9 <PID>

# 或使用一键清理
lsof -ti:7001 | xargs kill -9
```

## 性能优化建议

### 1. 模型预加载

首次启动服务后，访问一次 OCR 接口预加载模型：

```bash
curl -X POST http://localhost:7001/api/ocr/parse-bet-image \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer TOKEN" \
  -d '{"image_base64": "..."}'
```

### 2. 图片优化

- 上传前压缩图片（前端已配置 `sizeType: ['compressed']`）
- 建议分辨率：800x600 - 1920x1080
- 避免超大图片（>2000px 会自动缩放）

### 3. 并发控制

- OCR 识别为 CPU 密集型任务
- 建议限制并发请求数（Nginx 配置）
- 考虑使用队列处理大量请求

## 文件结构

```
football-betting-system/
├── api-service/
│   ├── main.py                 # FastAPI 主程序
│   ├── ocr_service.py          # OCR 识别服务
│   ├── bet_parser.py           # 投注信息解析
│   ├── test_ocr.py             # 单元测试
│   ├── test_ocr_debug.py       # 调试脚本
│   ├── test_image_ocr.sh       # 图片测试脚本
│   └── requirements.txt        # Python 依赖
│
├── frontend/
│   └── src/
│       ├── pages/
│       │   └── record/
│       │       ├── ocr-upload.vue  # OCR 上传页面
│       │       └── record.vue      # 投注记录页面
│       └── utils/
│           └── http.js             # HTTP 请求工具
│
└── OCR_FEATURE.md              # 本文档
```

## 版本信息

- **PaddleOCR**: 3.3.2
- **PaddlePaddle**: 3.0.0
- **OpenCV**: 4.12.0
- **Pillow**: 11.3.0
- **FastAPI**: 0.110.0+
- **Python**: 3.9+

## 更新日志

### 2025-11-26
- ✅ 实现 OCR 图片识别功能
- ✅ 集成 PaddleOCR 3.3.2
- ✅ 兼容新旧两种返回格式
- ✅ 实现投注信息解析
- ✅ 前端 H5 和小程序支持
- ✅ 添加详细日志记录
- ✅ 增加超时时间到 60 秒

## 技术支持

如有问题，请查看：
1. 后端日志：`/tmp/api-service.log`
2. 前端日志：`/tmp/frontend.log`
3. 系统日志：`sudo journalctl -u football-betting-api`

或参考 WARP.md 中的部署说明。
