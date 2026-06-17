import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from research_agent.tools.arxiv_tool import search_arxiv, format_papers
from research_agent.tools.semantic_scholar_tool import search_semantic_scholar
from research_agent.tools.pdf_tool import fetch_fulltext
from research_agent.config import (
    MAX_SEARCH_RESULTS, MAX_TOTAL_PAPERS,
    ENABLE_FULLTEXT, FULLTEXT_TOP_N, FULLTEXT_MAX_CHARS,
)


def search(queries: list[str], year_from: int | None = None) -> tuple[list[dict], str]:
    seen_urls: set[str] = set()
    all_papers: list[dict] = []

    # arXiv 并行（容忍并发）
    def fetch_arxiv(query: str) -> list[dict]:
        try:
            return search_arxiv(query, max_results=MAX_SEARCH_RESULTS)
        except RuntimeError as e:
            print(f"   ⚠️  arXiv [{query}]: {e}")
            return []

    with ThreadPoolExecutor(max_workers=len(queries)) as pool:
        for results in pool.map(fetch_arxiv, queries):
            for p in results:
                if p["url"] not in seen_urls:
                    seen_urls.add(p["url"])
                    all_papers.append(p)

    # Semantic Scholar 串行（免费 API 限制 ~1 req/s）
    for i, query in enumerate(queries):
        if i > 0:
            time.sleep(1.1)
        try:
            for p in search_semantic_scholar(
                query, max_results=MAX_SEARCH_RESULTS, year_from=year_from
            ):
                if p["url"] not in seen_urls:
                    seen_urls.add(p["url"])
                    all_papers.append(p)
        except RuntimeError as e:
            print(f"   ⚠️  Semantic Scholar [{query}]: {e}")

    # 引用数高的排前面，没有引用数字段的（arXiv）默认 0
    all_papers.sort(key=lambda p: p.get("citation_count", 0), reverse=True)

    # 截断到总量上限，避免 prompt 过长
    if len(all_papers) > MAX_TOTAL_PAPERS:
        print(f"   ℹ️  共 {len(all_papers)} 篇，截断到引用数前 {MAX_TOTAL_PAPERS} 篇")
        all_papers = all_papers[:MAX_TOTAL_PAPERS]

    # 给引用数 Top N 篇补全文（仅开源，闭源跳过并打标）
    if ENABLE_FULLTEXT:
        print(f"\n📄 尝试下载 Top {FULLTEXT_TOP_N} 篇全文...")
        with ThreadPoolExecutor(max_workers=FULLTEXT_TOP_N) as pool:
            top_papers = all_papers[:FULLTEXT_TOP_N]
            futures = {pool.submit(fetch_fulltext, p.get("pdf_url"), FULLTEXT_MAX_CHARS, p.get("title", "")): p
                       for p in top_papers}
            for future in as_completed(futures):
                paper = futures[future]
                text = future.result()
                if text:
                    paper["fulltext"] = text
                    print(f"   ✅ {paper['title'][:60]}...")
                else:
                    paper["needs_manual"] = True
                    print(f"   ⚠️  闭源/失败: {paper['title'][:60]}...")

    formatted = format_papers(all_papers)
    return all_papers, formatted
