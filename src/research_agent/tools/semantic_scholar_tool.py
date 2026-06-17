import time
import hashlib
import requests
import diskcache
from typing import List, Dict
from research_agent.config import CACHE_DIR, CACHE_TTL_SECONDS, PROXIES

_SESSION: requests.Session | None = None
_cache = diskcache.Cache(f"{CACHE_DIR}/semantic_scholar")

FIELDS = "title,authors,abstract,year,citationCount,externalIds,venue,openAccessPdf"


def _get_session() -> requests.Session:
    global _SESSION
    if _SESSION is None:
        _SESSION = requests.Session()
    return _SESSION


def search_semantic_scholar(
    query: str,
    max_results: int = 10,
    year_from: int | None = None,
    retries: int = 2,
    use_cache: bool = True,
) -> List[Dict]:
    key = hashlib.md5(f"s2|{query}|{max_results}|{year_from}".encode()).hexdigest()
    if use_cache and key in _cache:
        return _cache[key]

    session = _get_session()
    params = {
        "query": query,
        "limit": max_results,
        "fields": FIELDS,
    }
    if year_from:
        params["year"] = f"{year_from}-"

    for attempt in range(retries):
        try:
            resp = session.get(
                "https://api.semanticscholar.org/graph/v1/paper/search",
                params=params,
                timeout=8,
                proxies=PROXIES,
            )
            resp.raise_for_status()
            data = resp.json().get("data", [])
            results = []
            for p in data:
                if not p.get("abstract"):
                    continue
                ids = p.get("externalIds") or {}
                url = (
                    f"https://arxiv.org/abs/{ids['ArXiv']}"
                    if "ArXiv" in ids
                    else f"https://www.semanticscholar.org/paper/{p['paperId']}"
                )
                oa_pdf = (p.get("openAccessPdf") or {}).get("url")
                results.append({
                    "title": p.get("title", ""),
                    "authors": [a["name"] for a in (p.get("authors") or [])[:3]],
                    "abstract": p.get("abstract", ""),
                    "url": url,
                    "published": str(p.get("year", "N/A")),
                    "citation_count": p.get("citationCount", 0),
                    "venue": p.get("venue", ""),
                    "pdf_url": oa_pdf,   # 闭源则为 None
                })
            if use_cache:
                _cache.set(key, results, expire=CACHE_TTL_SECONDS)
            return results
        except requests.RequestException as e:
            if attempt == retries - 1:
                raise RuntimeError(f"Semantic Scholar 搜索失败（查询：{query}）：{e}") from e
            # 429 限速时等更久
            wait = 3 * (attempt + 1) if "429" in str(e) else 2 ** attempt
            print(f"   ⚠️  Semantic Scholar 请求失败 ({type(e).__name__})，{wait}s 后重试...")
            time.sleep(wait)
    return []
