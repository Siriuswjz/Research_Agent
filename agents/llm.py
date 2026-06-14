import time
import hashlib
import diskcache
from openai import OpenAI, APIConnectionError, APIStatusError
from config import DEEPSEEK_API_KEY, DEEPSEEK_BASE_URL, DEEPSEEK_MODEL, MAX_TOKENS, CACHE_DIR, CACHE_TTL_SECONDS

_cache = diskcache.Cache(f"{CACHE_DIR}/llm")

_client: OpenAI | None = None


def get_client() -> OpenAI:
    global _client
    if _client is None:
        _client = OpenAI(api_key=DEEPSEEK_API_KEY, base_url=DEEPSEEK_BASE_URL)
    return _client


def chat(system: str, user: str, retries: int = 3, use_cache: bool = True) -> str:
    key = hashlib.md5(f"{DEEPSEEK_MODEL}|{system}|{user}".encode()).hexdigest()
    if use_cache and key in _cache:
        return _cache[key]

    client = get_client()
    for attempt in range(retries):
        try:
            resp = client.chat.completions.create(
                model=DEEPSEEK_MODEL,
                max_tokens=MAX_TOKENS,
                messages=[
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
            )
            content = resp.choices[0].message.content
            if use_cache:
                _cache.set(key, content, expire=CACHE_TTL_SECONDS)
            return content
        except APIConnectionError as e:
            if attempt == retries - 1:
                raise RuntimeError(f"无法连接到 API，请检查网络：{e}") from e
        except APIStatusError as e:
            if e.status_code == 429:
                wait = 2 ** attempt
                print(f"   ⚠️  触发限速，{wait}s 后重试...")
                time.sleep(wait)
            elif attempt == retries - 1:
                raise RuntimeError(f"API 错误 {e.status_code}：{e.message}") from e
    raise RuntimeError("API 调用失败，已达最大重试次数")
