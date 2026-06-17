import os
import re
import hashlib
import requests
import diskcache
import fitz  # pymupdf
from research_agent.config import CACHE_DIR, CACHE_TTL_SECONDS, PDF_DIR, PROXIES

_cache = diskcache.Cache(f"{CACHE_DIR}/pdf_text")
os.makedirs(PDF_DIR, exist_ok=True)


def _slugify(title: str, max_len: int = 60) -> str:
    s = re.sub(r"[^\w\s-]", "", title.lower())
    s = re.sub(r"[\s_-]+", "-", s).strip("-")
    return s[:max_len] or "untitled"


def download_pdf(url: str, timeout: int = 60) -> bytes | None:
    """下载 PDF，失败返回 None；打印失败原因便于调试"""
    headers = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                      "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36"
    }
    try:
        r = requests.get(url, timeout=timeout, allow_redirects=True, headers=headers, proxies=PROXIES)
        r.raise_for_status()
        if not r.content.startswith(b"%PDF"):
            print(f"      ↳ 不是 PDF（可能是登录页/HTML），开头: {r.content[:20]!r}")
            return None
        return r.content
    except requests.Timeout:
        print(f"      ↳ 超时（{timeout}s）: {url}")
        return None
    except requests.HTTPError as e:
        print(f"      ↳ HTTP {e.response.status_code}: {url}")
        return None
    except Exception as e:
        print(f"      ↳ 失败 {type(e).__name__}: {e}")
        return None


def parse_pdf(content: bytes, max_chars: int) -> str:
    """用 PyMuPDF 抽出纯文本，截断到 max_chars"""
    try:
        with fitz.open(stream=content, filetype="pdf") as doc:
            text = "\n".join(page.get_text() for page in doc)
        text = " ".join(text.split())  # 去掉多余空白
        return text[:max_chars]
    except Exception:
        return ""


def fetch_fulltext(pdf_url: str, max_chars: int, title: str = "") -> str | None:
    """下载 + 解析 + 保存 PDF 到 PDF_DIR。失败返回 None"""
    if not pdf_url:
        return None
    key = hashlib.md5(f"{pdf_url}|{max_chars}".encode()).hexdigest()
    if key in _cache:
        return _cache[key]

    content = download_pdf(pdf_url)
    if content is None:
        return None

    # 保存 PDF 到磁盘，文件名 = 标题 slug + url hash 防冲突
    filename = f"{_slugify(title)}_{key[:8]}.pdf" if title else f"{key}.pdf"
    pdf_path = os.path.join(PDF_DIR, filename)
    if not os.path.exists(pdf_path):
        with open(pdf_path, "wb") as f:
            f.write(content)

    text = parse_pdf(content, max_chars)
    if not text:
        return None

    _cache.set(key, text, expire=CACHE_TTL_SECONDS)
    return text
