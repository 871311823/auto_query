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
from urllib.error import HTTPError

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


def _post_chat_completion(cfg, messages, max_tokens, temperature, timeout):
    """发 /chat/completions 请求，返回 (ok, content_or_errmsg)。

    根据服务端错误自适应降级重试，兼容不同模型的参数限制：
    - 默认用 max_tokens + temperature（DeepSeek 等多数 OpenAI 兼容模型）
    - 若报错提示不支持 max_tokens、要求 max_completion_tokens，则换参数名
    - 若报错提示 temperature 取值不支持（如 Azure 后端 GPT-5.6 只接受默认值），则去掉 temperature
    """
    url = cfg["base_url"] + "/chat/completions"
    headers = {
        "User-Agent": UA,
        "Content-Type": "application/json",
        "Authorization": f"Bearer {cfg['api_key']}",
    }
    ctx = ssl._create_unverified_context()

    token_param = "max_tokens"
    use_temperature = True
    for _ in range(4):
        payload_dict = {"model": cfg["model"], "messages": messages, token_param: max_tokens}
        if use_temperature:
            payload_dict["temperature"] = temperature
        payload = json.dumps(payload_dict).encode("utf-8")
        try:
            req = urllib.request.Request(url, data=payload, headers=headers)
            with urllib.request.urlopen(req, timeout=timeout, context=ctx) as resp:
                body = resp.read().decode("utf-8")
                data = json.loads(body)
                content = data["choices"][0]["message"]["content"]
                return True, content
        except HTTPError as e:
            detail = ""
            try:
                detail = e.read().decode("utf-8", "replace")
            except Exception:
                pass
            # 按错误类型决定下一次重试的修正方向
            if token_param == "max_tokens" and "max_completion_tokens" in detail:
                token_param = "max_completion_tokens"
                continue
            if use_temperature and "temperature" in detail:
                use_temperature = False
                continue
            return False, f"HTTP {e.code}：{detail[:200] or '无错误详情'}"
        except Exception as e:
            return False, f"{type(e).__name__}：{str(e)[:200]}"
    return False, "请求失败：多次调整参数后仍无法调用该模型"


def chat_completion(messages, max_tokens=32768, temperature=0.1):
    """调用配置的 LLM 接口（OpenAI 兼容 /chat/completions），返回响应文本"""
    cfg = _load_llm_config()
    if not cfg["api_key"]:
        import sys
        print("[LLM_ERROR] 未配置 API Key，请到「接口配置」页设置", file=sys.stderr)
        return None
    _rate_limit()
    ok, content = _post_chat_completion(cfg, messages, max_tokens, temperature, 600)
    if not ok:
        import sys
        print(f"[LLM_ERROR] {content}", file=sys.stderr)
        return None
    return content


def test_connection(base_url=None, api_key=None, model=None, timeout=30):
    """测试接口连通性与 prompt 调用是否正常，返回 (ok, message)。

    使用传入的参数直接发一次最小化 chat/completions 请求，不触碰全局运行时配置，
    用于「接口配置」保存前的连通性验证。
    """
    cfg = {
        "base_url": (base_url or "").strip().rstrip("/") or DEFAULT_BASE_URL,
        "api_key": (api_key or "").strip(),
        "model": (model or "").strip() or DEFAULT_MODEL,
    }
    if not cfg["api_key"]:
        return False, "未配置 API Key，请先填写模型接口的 API Key"

    messages = [
        {"role": "system", "content": "你是接口连通性测试助手。"},
        {"role": "user", "content": "请只回复两个字：OK"},
    ]
    ok, content = _post_chat_completion(cfg, messages, 16, 0, timeout)
    if not ok:
        return False, content
    if not content or not str(content).strip():
        return False, "接口已连通，但模型未返回任何内容"
    return True, str(content).strip()[:80]


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
