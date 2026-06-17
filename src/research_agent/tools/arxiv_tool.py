import time
import hashlib
import arxiv
import diskcache
from typing import List, Dict
from research_agent.config import CACHE_DIR, CACHE_TTL_SECONDS

_arxiv_client: arxiv.Client | None = None
_cache = diskcache.Cache(f"{CACHE_DIR}/arxiv")


def _get_arxiv_client() -> arxiv.Client:
    global _arxiv_client
    if _arxiv_client is None:
        _arxiv_client = arxiv.Client()
    return _arxiv_client


def search_arxiv(query: str, max_results: int = 5, retries: int = 3, use_cache: bool = True) -> List[Dict]:
    """搜索 Arxiv 论文，返回结构化结果列表"""
    key = hashlib.md5(f"arxiv|{query}|{max_results}".encode()).hexdigest()
    if use_cache and key in _cache:
        return _cache[key]

    client = _get_arxiv_client()
    search = arxiv.Search(
        query=query,
        max_results=max_results,
        sort_by=arxiv.SortCriterion.Relevance,
    )
    for attempt in range(retries):
        try:
            results = []
            for paper in client.results(search):
                results.append({
                    "title": paper.title,
                    "authors": [a.name for a in paper.authors[:3]],
                    "abstract": paper.summary,
                    "url": paper.entry_id,
                    "published": str(paper.published.date()),
                    "pdf_url": paper.pdf_url,   # arxiv 都开源
                })
            if use_cache:
                _cache.set(key, results, expire=CACHE_TTL_SECONDS)
            return results
        except Exception as e:
            if attempt == retries - 1:
                raise RuntimeError(f"Arxiv 搜索失败（查询：{query}）：{e}") from e
            wait = 2 ** attempt
            print(f"   ⚠️  Arxiv 请求失败，{wait}s 后重试...")
            time.sleep(wait)
    return []


def format_papers(papers: List[Dict]) -> str:
    """把论文列表格式化成可读文本，供 LLM 使用"""
    lines = []
    for i, p in enumerate(papers, 1):
        venue = p.get("venue", "")
        citation = p.get("citation_count")
        meta_parts = [venue]
        if citation is not None:
            meta_parts.append(f"被引 {citation} 次")
        if p.get("needs_manual"):
            meta_parts.append("⚠️ 闭源，需手动下载")
        meta = " | ".join(filter(None, meta_parts))

        # 有全文用全文，没有用摘要
        body = p.get("fulltext")
        body_label = "全文摘录" if body else "摘要"
        if not body:
            body = (p.get("abstract") or "")[:300] + "..."

        lines.append(
            f"[{i}] {p['title']}\n"
            f"    作者: {', '.join(p['authors'])}\n"
            f"    发表: {p['published']}"
            + (f" | {meta}" if meta else "") + "\n"
            f"    {body_label}: {body}\n"
            f"    链接: {p['url']}\n"
        )
    return "\n".join(lines)
