"""大模型调用配置(统一入口)。默认直连 DeepSeek; 配置环境变量即可切到网关而不改代码:

  DEEPSEEK_API_KEY       密钥(网关 key 也用这个名字, 沿用既有配置)
  LLM_OPENAI_BASE_URL    OpenAI 兼容接口根地址(SDK 会拼 /chat/completions), 网关: https://tokenapi.happyelements.net/v1
  LLM_OPENAI_MODEL       OpenAI 兼容接口的模型名, 网关: deepseek/deepseek-v4-flash
  LLM_ANTHROPIC_URL      Anthropic 兼容接口完整地址(聊天用, 支持联网搜索/图片/流式), 网关: https://tokenapi.happyelements.net/v1/messages
  LLM_ANTHROPIC_MODEL    Anthropic 兼容接口的模型名, 网关: deepseek/deepseek-v4-flash-anthropic

旧变量 DEEPSEEK_BASE_URL / DEEPSEEK_MODEL / MATCH_CHAT_MODEL 仍作为回退。
"""
import os

_LEGACY_BASE = os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com").rstrip("/")

OPENAI_BASE = os.getenv("LLM_OPENAI_BASE_URL", "").rstrip("/") or _LEGACY_BASE
OPENAI_MODEL = os.getenv("LLM_OPENAI_MODEL", "") or os.getenv("DEEPSEEK_MODEL", "deepseek-flash")
ANTHROPIC_URL = os.getenv("LLM_ANTHROPIC_URL", "") or f"{_LEGACY_BASE}/anthropic/v1/messages"
ANTHROPIC_MODEL = os.getenv("LLM_ANTHROPIC_MODEL", "") or os.getenv("MATCH_CHAT_MODEL", "deepseek-flash")
