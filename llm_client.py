import time

_last_request_time = 0
_min_interval = 1.0


def _rate_limit():
    global _last_request_time
    now = time.time()
    elapsed = now - _last_request_time
    if elapsed < _min_interval:
        time.sleep(_min_interval - elapsed)
    _last_request_time = time.time()

import json
import os
import ssl
import urllib.request
import urllib.parse

DEFAULT_BASE_URL = "https://api.deepseek.com"
DEFAULT_API_KEY = ""
DEFAULT_MODEL = "deepseek-v4-flash"

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
_runtime_cfg = {"base_url": "", "api_key": "", "model": ""}


def set_llm_config(base_url=None, api_key=None, model=None):
    """运行期注入接口配置（仅内存，不落盘）"""
    if base_url is not None:
        _runtime_cfg["base_url"] = (base_url or "").strip().rstrip("/")
    if api_key is not None:
        _runtime_cfg["api_key"] = (api_key or "").strip()
    if model is not None:
        _runtime_cfg["model"] = (model or "").strip()


def _load_llm_config():
    return {
        "base_url": _runtime_cfg.get("base_url") or DEFAULT_BASE_URL,
        "api_key": _runtime_cfg.get("api_key", ""),
        "model": _runtime_cfg.get("model") or DEFAULT_MODEL,
    }


def chat_completion(messages, max_tokens=32768, temperature=0.1):
    """调用配置的 LLM 接口（OpenAI 兼容 /chat/completions），返回响应文本"""
    cfg = _load_llm_config()
    if not cfg["api_key"]:
        import sys
        print("[LLM_ERROR] 未配置 API Key，请到「接口配置」页设置", file=sys.stderr)
        return None
    url = cfg["base_url"] + "/chat/completions"
    payload = json.dumps({
        "model": cfg["model"],
        "messages": messages,
        "max_tokens": max_tokens,
        "temperature": temperature,
    }).encode("utf-8")

    headers = {
        "User-Agent": UA,
        "Content-Type": "application/json",
        "Authorization": f"Bearer {cfg['api_key']}",
    }

    _rate_limit()
    ctx = ssl._create_unverified_context()
    try:
        req = urllib.request.Request(url, data=payload, headers=headers)
        with urllib.request.urlopen(req, timeout=600, context=ctx) as resp:
            body = resp.read().decode("utf-8")
            data = json.loads(body)
            return data["choices"][0]["message"]["content"]
    except Exception as e:
        import sys
        print(f"[LLM_ERROR] {type(e).__name__}: {str(e)[:200]}", file=sys.stderr)
        return None


def evaluate_items(system_prompt, user_content):
    """调用 LLM 评估条目，返回模型输出的原始文本"""
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_content},
    ]
    return chat_completion(messages)


if __name__ == "__main__":
    # 快速测试
    r = chat_completion([
        {"role": "system", "content": "你是一个测试助手，请用中文回答。"},
        {"role": "user", "content": "你好，回复一句话即可。"},
    ])
    print(r)
