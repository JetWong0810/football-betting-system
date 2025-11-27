"""OCR图片识别服务模块

使用PaddleOCR进行图片文字识别
"""
import logging
from typing import List, Dict, Any, Optional, Tuple, Union
import base64
import io
from PIL import Image
import cv2
import numpy as np

logger = logging.getLogger(__name__)

# 延迟导入PaddleOCR，避免启动时加载耗时
_ocr_instance = None


def get_ocr_instance():
    """获取OCR实例（单例模式）"""
    global _ocr_instance
    if _ocr_instance is None:
        try:
            from paddleocr import PaddleOCR
            # PaddleOCR 3.x 极速配置（使用轻量级mobile模型）
            # 关键优化：
            # 1. 使用mobile模型而非server模型（速度提升 5-10x！）
            # 2. 禁用所有不必要的检测步骤
            # 3. 降低分辨率限制
            _ocr_instance = PaddleOCR(
                # 使用轻量级模型（最关键的优化！）
                text_detection_model_name='PP-OCRv4_mobile_det',
                text_recognition_model_name='PP-OCRv4_mobile_rec',
                # 禁用不必要的功能
                use_textline_orientation=False,
                use_doc_orientation_classify=False,
                use_doc_unwarping=False,
                # 性能优化参数
                text_recognition_batch_size=8,
                text_det_limit_side_len=800,  # 进一步降低
                lang='ch'
            )
            logger.info("PaddleOCR初始化成功（已启用性能优化）")
        except Exception as e:
            logger.error(f"PaddleOCR初始化失败: {e}")
            raise RuntimeError(f"OCR引擎初始化失败: {e}")
    return _ocr_instance


def preprocess_image(image: Image.Image, fast_mode: bool = True) -> np.ndarray:
    """图片预处理，提高OCR识别准确率
    
    Args:
        image: PIL Image对象
        fast_mode: 快速模式，跳过耗时的降噪和增强步骤
        
    Returns:
        处理后的numpy数组（OpenCV格式）
    """
    # 转换为numpy数组
    img_array = np.array(image)
    
    # 如果是RGBA，转换为RGB
    if len(img_array.shape) == 3 and img_array.shape[2] == 4:
        img_array = cv2.cvtColor(img_array, cv2.COLOR_RGBA2RGB)
    
    # 如果是灰度图，转换为RGB
    if len(img_array.shape) == 2:
        img_array = cv2.cvtColor(img_array, cv2.COLOR_GRAY2RGB)
    
    # 转换为OpenCV BGR格式
    img_bgr = cv2.cvtColor(img_array, cv2.COLOR_RGB2BGR)
    
    # 快速模式：跳过耗时的图像增强
    if fast_mode:
        return img_bgr
    
    # 完整模式：应用图像增强（更准确但更慢）
    gray = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2GRAY)
    
    # 简化的对比度增强（比CLAHE更快）
    enhanced = cv2.equalizeHist(gray)
    
    # 转回BGR格式
    result = cv2.cvtColor(enhanced, cv2.COLOR_GRAY2BGR)
    
    return result


def parse_base64_image(base64_str: str) -> Image.Image:
    """解析base64编码的图片
    
    Args:
        base64_str: base64编码的图片字符串
        
    Returns:
        PIL Image对象
    """
    try:
        # 移除可能存在的data URL前缀
        if ',' in base64_str:
            base64_str = base64_str.split(',', 1)[1]
        
        image_data = base64.b64decode(base64_str)
        image = Image.open(io.BytesIO(image_data))
        return image
    except Exception as e:
        logger.error(f"解析base64图片失败: {e}")
        raise ValueError(f"图片格式错误: {e}")


def parse_file_image(file_bytes: bytes) -> Image.Image:
    """解析上传的文件图片
    
    Args:
        file_bytes: 图片文件字节数据
        
    Returns:
        PIL Image对象
    """
    try:
        image = Image.open(io.BytesIO(file_bytes))
        return image
    except Exception as e:
        logger.error(f"解析文件图片失败: {e}")
        raise ValueError(f"图片格式错误: {e}")


def extract_text_from_image(
    image: Image.Image,
    preprocess: bool = False,  # 默认关闭预处理以提升速度
    fast_mode: bool = True
) -> Tuple[str, List[Dict[str, Any]], float]:
    """从图片中提取文字
    
    Args:
        image: PIL Image对象
        preprocess: 是否进行图片预处理
        
    Returns:
        Tuple[全文本, OCR详细结果列表, 平均置信度]
        OCR详细结果格式：[{
            "text": "识别的文字",
            "confidence": 0.95,
            "box": [[x1,y1], [x2,y2], [x3,y3], [x4,y4]]  # 文字区域坐标
        }]
    """
    try:
        ocr = get_ocr_instance()
        
        # 图片预处理
        if preprocess:
            img_array = preprocess_image(image, fast_mode=fast_mode)
        else:
            img_array = np.array(image)
            if len(img_array.shape) == 3 and img_array.shape[2] == 4:
                img_array = cv2.cvtColor(img_array, cv2.COLOR_RGBA2RGB)
            img_array = cv2.cvtColor(img_array, cv2.COLOR_RGB2BGR)
        
        # 调用PaddleOCR识别（PaddleOCR 3.x 版本不支持 cls 参数）
        result = ocr.ocr(img_array)
        
        logger.info(f"OCR原始结果类型: {type(result)}")
        
        # PaddleOCR 3.x 返回新格式：字典列表
        if not result:
            logger.warning("OCR未识别到任何文字")
            return "", [], 0.0
        
        # 解析OCR结果
        texts = []
        details = []
        confidences = []
        
        # 处理新版 PaddleOCR 3.x 的返回格式
        if isinstance(result, list) and len(result) > 0:
            first_item = result[0]
            
            # 新版本：返回字典格式
            if isinstance(first_item, dict):
                logger.info("检测到 PaddleOCR 3.x 新格式")
                
                # 提取识别结果
                rec_texts = first_item.get('rec_texts', [])
                rec_scores = first_item.get('rec_scores', [])
                rec_polys = first_item.get('rec_polys', [])
                
                logger.info(f"识别到 {len(rec_texts)} 行文字")
                
                for i, text in enumerate(rec_texts):
                    confidence = rec_scores[i] if i < len(rec_scores) else 0.9
                    box = rec_polys[i].tolist() if i < len(rec_polys) else []
                    
                    texts.append(text)
                    confidences.append(confidence)
                    details.append({
                        "text": text,
                        "confidence": confidence,
                        "box": box
                    })
            
            # 旧版本：[box, (text, confidence)] 格式
            elif isinstance(first_item, list):
                logger.info("检测到 PaddleOCR 旧格式")
                for line in result[0]:
                    try:
                        box = line[0]
                        if isinstance(line[1], tuple) and len(line[1]) >= 2:
                            text = line[1][0]
                            confidence = line[1][1]
                        elif isinstance(line[1], str):
                            text = line[1]
                            confidence = 0.9
                        else:
                            text = str(line[1])
                            confidence = 0.9
                        
                        texts.append(text)
                        confidences.append(confidence)
                        details.append({
                            "text": text,
                            "confidence": confidence,
                            "box": box
                        })
                    except (IndexError, TypeError) as e:
                        logger.warning(f"解析 OCR 结果失败: {e}")
                        continue
        
        # 合并所有文本，用空格分隔
        full_text = " ".join(texts)
        
        # 计算平均置信度
        avg_confidence = sum(confidences) / len(confidences) if confidences else 0.0
        
        logger.info(f"OCR识别成功，识别{len(texts)}行文字，平均置信度: {avg_confidence:.2f}")
        
        return full_text, details, avg_confidence
        
    except Exception as e:
        logger.error(f"OCR识别失败: {e}", exc_info=True)
        raise RuntimeError(f"OCR识别失败: {e}")


def recognize_image(
    image_source: Union[str, bytes],
    source_type: str = "base64"
) -> Dict[str, Any]:
    """识别图片中的文字（统一入口）
    
    Args:
        image_source: 图片来源（base64字符串或文件字节）
        source_type: 来源类型，'base64' 或 'file'
        
    Returns:
        {
            "success": True,
            "text": "识别的完整文本",
            "details": [OCR详细结果],
            "confidence": 0.92
        }
    """
    try:
        # 解析图片
        if source_type == "base64":
            image = parse_base64_image(image_source)
        elif source_type == "file":
            image = parse_file_image(image_source)
        else:
            raise ValueError(f"不支持的来源类型: {source_type}")
        
        # 检查图片尺寸，如果太大则缩放（更积极的缩放策略以提升速度）
        max_size = 1600  # 降低最大尺寸限制，加快处理速度
        if max(image.size) > max_size:
            ratio = max_size / max(image.size)
            new_size = (int(image.size[0] * ratio), int(image.size[1] * ratio))
            # 使用更快的缩放算法
            image = image.resize(new_size, Image.Resampling.BILINEAR)
            logger.info(f"图片已缩放到 {new_size}")
        
        # 提取文字（关闭预处理以提升速度，PaddleOCR本身已经足够强大）
        full_text, details, confidence = extract_text_from_image(image, preprocess=False, fast_mode=True)
        
        return {
            "success": True,
            "text": full_text,
            "details": details,
            "confidence": round(confidence, 4)
        }
        
    except ValueError as e:
        # 图片格式错误等用户输入问题
        return {
            "success": False,
            "error": str(e),
            "text": "",
            "details": [],
            "confidence": 0.0
        }
    except Exception as e:
        # 其他系统错误
        logger.error(f"图片识别失败: {e}", exc_info=True)
        return {
            "success": False,
            "error": f"识别失败: {str(e)}",
            "text": "",
            "details": [],
            "confidence": 0.0
        }
