"""
从 pdfs/ 里筛选过的论文生成详细综述。

用法：
    research-agent-write "我的研究问题"
    research-agent-write "我的研究问题" path/to/folder/
    research-agent-write "我的研究问题" --skip-critic   # 跳过 Critic 审查
    research-agent-write "我的研究问题" --no-cache      # 强制重新解析所有 PDF
"""
import os
import re
import sys
import json
import hashlib
from datetime import datetime

from research_agent.tools.marker_tool import parse_pdf_high_quality, is_marker_available
from research_agent.tools.gpu_utils import describe_device, pick_free_gpus
from research_agent.agents.synthesizer import synthesize
from research_agent.agents.critic import review, revise
from research_agent.config import PDF_DIR, FULLTEXT_MAX_CHARS, CACHE_DIR


CURATED_CACHE_DIR = os.path.join(CACHE_DIR, "curated")


def _slugify(s: str, max_len: int = 40) -> str:
    s = re.sub(r"[^\w\s-]", "", s.lower())
    s = re.sub(r"[\s_-]+", "-", s).strip("-")
    return s[:max_len] or "curated"


def _extract_title(text: str, fallback: str) -> str:
    for line in text.strip().splitlines():
        line = line.strip()
        if 15 <= len(line) <= 250 and not line.lower().startswith(("abstract", "introduction")):
            return line
    return fallback


def _format_papers_for_critic(papers: list[dict]) -> str:
    """供 Critic 检查覆盖度 / 引用正确性"""
    return "\n\n".join(
        f"[{i}] {p['title']}\n    源文件: {p['source_file']}\n    全文摘录（前 500 字）: {p['fulltext'][:500]}..."
        for i, p in enumerate(papers, 1)
    )


def _stage_key(question: str, pdfs: list[str]) -> str:
    """为 (问题, PDF 列表 + 修改时间) 生成稳定 hash 作为缓存 key"""
    parts = [question]
    for p in pdfs:
        try:
            parts.append(f"{p}|{os.path.getmtime(p)}")
        except OSError:
            parts.append(p)
    return hashlib.md5("\n".join(parts).encode()).hexdigest()[:12]


def _parse_phase(pdfs: list[str], cache_key: str, use_cache: bool) -> list[dict]:
    """解析阶段：逐篇解析 PDF，每篇成功就追加到中间缓存。崩了重跑可以续上。"""
    os.makedirs(CURATED_CACHE_DIR, exist_ok=True)
    cache_path = os.path.join(CURATED_CACHE_DIR, f"{cache_key}_parsed.json")

    if use_cache and os.path.exists(cache_path):
        with open(cache_path, encoding="utf-8") as f:
            cached = json.load(f)
        done_files = {p["source_file"] for p in cached}
        if done_files == set(pdfs):
            print(f"♻️  完整命中解析缓存：{cache_path}（{len(cached)} 篇）")
            return cached
        print(f"♻️  部分命中解析缓存（{len(done_files)} 篇已解析），续跑剩余")
    else:
        cached = []
        done_files = set()

    for i, path in enumerate(pdfs, 1):
        if path in done_files:
            continue
        fname = os.path.basename(path)
        print(f"[{i}/{len(pdfs)}] {fname[:70]}")
        text = parse_pdf_high_quality(path)
        if not text.strip():
            print(f"   ⚠️  解析为空，跳过")
            continue
        title = _extract_title(text, fname.replace(".pdf", ""))
        cached.append({
            "title": title,
            "fulltext": text[:FULLTEXT_MAX_CHARS],
            "source_file": path,
        })
        # 每解析完一篇立即写盘，崩了不丢
        with open(cache_path, "w", encoding="utf-8") as f:
            json.dump(cached, f, ensure_ascii=False, indent=2)

    return cached


def _synthesize_phase(question: str, papers: list[dict], cache_key: str, use_cache: bool) -> str:
    """合成阶段：调 Synthesizer LLM。结果落盘可恢复"""
    cache_path = os.path.join(CURATED_CACHE_DIR, f"{cache_key}_draft.md")
    if use_cache and os.path.exists(cache_path):
        print(f"♻️  命中初稿缓存：{cache_path}")
        with open(cache_path, encoding="utf-8") as f:
            return f.read()

    draft = synthesize(question, papers)
    with open(cache_path, "w", encoding="utf-8") as f:
        f.write(draft)
    return draft


def _critic_phase(papers: list[dict], draft: str, cache_key: str, use_cache: bool) -> str:
    """Critic 审查 + 必要时 Revise"""
    cache_path = os.path.join(CURATED_CACHE_DIR, f"{cache_key}_final.md")
    if use_cache and os.path.exists(cache_path):
        print(f"♻️  命中终稿缓存：{cache_path}")
        with open(cache_path, encoding="utf-8") as f:
            return f.read()

    formatted = _format_papers_for_critic(papers)
    print("\n🧐 Critic：审查初稿...")
    issues = review(formatted, draft)
    if issues.strip().upper().startswith("PASS"):
        print("   ✅ 通过")
        final = draft
    else:
        print(f"   发现问题：\n{issues}")
        print("\n✍️  Synthesizer：根据 Critic 反馈修订...")
        final = revise(formatted, draft, issues)

    with open(cache_path, "w", encoding="utf-8") as f:
        f.write(final)
    return final


def main():
    args = sys.argv[1:]
    if not args:
        print('用法：research-agent-write "研究问题" [PDF目录] [--skip-critic] [--no-cache]')
        sys.exit(1)

    skip_critic = "--skip-critic" in args
    use_cache = "--no-cache" not in args
    args = [a for a in args if a not in ("--skip-critic", "--no-cache")]

    question = args[0]
    folder = args[1] if len(args) > 1 else PDF_DIR

    if not os.path.isdir(folder):
        print(f"❌ 目录不存在：{folder}")
        sys.exit(1)

    pdfs = sorted(
        os.path.join(folder, f) for f in os.listdir(folder)
        if f.lower().endswith(".pdf")
    )
    if not pdfs:
        print(f"❌ {folder} 下没有 PDF")
        sys.exit(1)

    # 在任何 torch import 之前选 GPU
    free_gpus = pick_free_gpus(1)
    if free_gpus:
        os.environ["CUDA_VISIBLE_DEVICES"] = str(free_gpus[0])

    print(f"📖 PDF 解析器：{'marker (高质量)' if is_marker_available() else 'PyMuPDF (快速)'}")
    print(f"💻 设备：{describe_device()}")
    if free_gpus:
        print(f"🎯 使用 GPU：{free_gpus[0]}")
    print(f"📄 找到 {len(pdfs)} 篇 PDF\n")

    cache_key = _stage_key(question, pdfs)
    print(f"🔑 任务 ID：{cache_key}（同问题+同文件 重跑可续）\n")

    # === Phase 1: 解析 ===
    papers = _parse_phase(pdfs, cache_key, use_cache)
    if not papers:
        print("\n❌ 没有任何论文能成功解析")
        sys.exit(1)

    # === Phase 2: 合成 ===
    print(f"\n✍️  Synthesizer 撰写详细综述（{len(papers)} 篇 → 目标 3000-5000 字）...")
    draft = _synthesize_phase(question, papers, cache_key, use_cache)

    # === Phase 3: Critic ===
    if skip_critic:
        final = draft
    else:
        final = _critic_phase(papers, draft, cache_key, use_cache)

    # === 输出 ===
    os.makedirs("reports", exist_ok=True)
    timestamp = datetime.now().strftime("%Y-%m-%d_%H%M%S")
    slug = _slugify(question)
    base = f"reports/{timestamp}_curated_{slug}"

    with open(f"{base}.md", "w", encoding="utf-8") as f:
        f.write(f"# {question}\n\n> 基于 `{folder}` 目录下 {len(papers)} 篇筛选论文生成\n\n{final}")

    meta = [{"title": p["title"], "source_file": p["source_file"]} for p in papers]
    with open(f"{base}_papers.json", "w", encoding="utf-8") as f:
        json.dump({"question": question, "source_folder": folder, "papers": meta},
                  f, ensure_ascii=False, indent=2)

    print(f"\n✅ 详细综述：{base}.md")
    print(f"   元数据：{base}_papers.json")
    print(f"   中间缓存：{CURATED_CACHE_DIR}/{cache_key}_*（重跑可秒级返回）")


if __name__ == "__main__":
    main()
