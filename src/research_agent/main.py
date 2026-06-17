from research_agent.agents.planner import plan, expand
from research_agent.agents.search import search
from research_agent.agents.writer import write
from research_agent.agents.critic import review, revise
from research_agent.config import MIN_PAPERS


def run(research_question: str) -> tuple[str, list[dict]]:
    print(f"\n🔍 研究问题：{research_question}\n")

    # Step 1: 规划搜索关键词
    print("📋 Planner：拆解搜索关键词...")
    domain, queries = plan(research_question)
    print(f"   领域识别：{domain}")
    for q in queries:
        print(f"   - {q}")

    # Step 2: 搜索论文
    print(f"\n📚 Search：检索 arXiv + Semantic Scholar（{len(queries)} 个查询）...")
    papers, formatted = search(queries)
    print(f"   找到 {len(papers)} 篇不重复论文")

    # Step 2.5: 反馈环 — 结果太少时让 Planner 补充关键词重搜
    if len(papers) < MIN_PAPERS:
        print(f"\n🔁 结果不足 {MIN_PAPERS} 篇，请 Planner 补充关键词...")
        new_queries = expand(research_question, queries, domain)
        if new_queries:
            for q in new_queries:
                print(f"   + {q}")
            extra_papers, _ = search(new_queries)
            # 合并去重
            seen = {p["url"] for p in papers}
            for p in extra_papers:
                if p["url"] not in seen:
                    papers.append(p)
                    seen.add(p["url"])
            papers.sort(key=lambda p: p.get("citation_count", 0), reverse=True)
            from tools.arxiv_tool import format_papers
            formatted = format_papers(papers)
            print(f"   补搜后共 {len(papers)} 篇")

    # Step 3: 生成综述
    print("\n✍️  Writer：生成综述初稿...")
    report = write(research_question, formatted)

    # Step 4: Critic 审查
    print("\n🧐 Critic：审查初稿...")
    issues = review(formatted, report)
    if issues.strip().upper().startswith("PASS"):
        print("   ✅ 通过")
    else:
        print(f"   发现问题：\n{issues}")
        print("\n✍️  Writer：根据 Critic 反馈修订...")
        report = revise(formatted, report, issues)

    return report, papers


def main():
    import os
    import re
    import json
    from datetime import datetime

    print("请输入你的研究问题（输入完按回车，然后输入 y 确认）：")
    question = input("> ").strip()
    if not question:
        question = "compressible turbulent boundary layer wall shear stress reconstruction using deep learning"
        print(f"使用默认问题：{question}")

    print(f"\n✅ 你输入的问题是：\n   {question}\n")
    confirm = input("确认开始？(y/n)：").strip().lower()
    if confirm not in ("y", "yes", ""):
        print("已取消")
        return

    result, papers = run(question)
    print("\n" + "=" * 60)
    print(result)
    print("=" * 60)

    os.makedirs("reports", exist_ok=True)
    slug = re.sub(r"[^\w\s-]", "", question.lower())
    slug = re.sub(r"[\s_-]+", "-", slug).strip("-")[:40]
    timestamp = datetime.now().strftime("%Y-%m-%d_%H%M%S")
    base = f"reports/{timestamp}_{slug}"

    with open(f"{base}.md", "w", encoding="utf-8") as f:
        f.write(f"# Research Report\n\n**问题**：{question}\n\n{result}")

    meta = [{k: v for k, v in p.items() if k != "fulltext"} for p in papers]
    with open(f"{base}_papers.json", "w", encoding="utf-8") as f:
        json.dump({"question": question, "papers": meta}, f, ensure_ascii=False, indent=2)

    print(f"\n✅ 报告：{base}.md")
    print(f"   元数据：{base}_papers.json（供 research-agent-read 精读用）")


if __name__ == "__main__":
    main()
