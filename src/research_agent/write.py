"""
从 pdfs/ 里筛选过的论文生成详细综述。

用法：
    research-agent-write "我的研究问题"
    research-agent-write "我的研究问题" path/to/folder/
"""
import os
import re
import sys
import json
from datetime import datetime

from research_agent.tools.marker_tool import parse_pdf_high_quality, is_marker_available
from research_agent.tools.gpu_utils import describe_device
from research_agent.agents.synthesizer import synthesize
from research_agent.config import PDF_DIR, FULLTEXT_MAX_CHARS


def _slugify(s: str, max_len: int = 40) -> str:
    s = re.sub(r"[^\w\s-]", "", s.lower())
    s = re.sub(r"[\s_-]+", "-", s).strip("-")
    return s[:max_len] or "curated"


def _extract_title(text: str, fallback: str) -> str:
    """从全文头部猜测论文标题：第一非空行，长度合理"""
    for line in text.strip().splitlines():
        line = line.strip()
        if 15 <= len(line) <= 250 and not line.lower().startswith(("abstract", "introduction")):
            return line
    return fallback


def main():
    args = sys.argv[1:]
    if not args:
        print('用法：research-agent-write "研究问题" [PDF目录]')
        sys.exit(1)

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

    # 单篇上限按总篇数动态分配，避免 prompt 太长
    # DeepSeek 类模型 128K 上下文，留余量给 prompt + 输出
    total_budget = 80_000
    per_paper = min(FULLTEXT_MAX_CHARS, max(2000, total_budget // len(pdfs)))

    print(f"📖 PDF 解析器：{'marker (高质量)' if is_marker_available() else 'PyMuPDF (快速)'}")
    print(f"💻 设备：{describe_device()}")
    print(f"📄 找到 {len(pdfs)} 篇 PDF（每篇最多取 {per_paper} 字符）\n")

    papers = []
    for i, path in enumerate(pdfs, 1):
        fname = os.path.basename(path)
        print(f"[{i}/{len(pdfs)}] {fname[:70]}")
        text = parse_pdf_high_quality(path)
        if not text.strip():
            print(f"   ⚠️  解析为空，跳过")
            continue
        title = _extract_title(text, fname.replace(".pdf", ""))
        papers.append({
            "title": title,
            "fulltext": text[:per_paper],
            "source_file": path,
        })

    if not papers:
        print("\n❌ 没有任何论文能成功解析")
        sys.exit(1)

    print(f"\n✍️  Synthesizer 撰写详细综述（{len(papers)} 篇 → 目标 3000-5000 字）...")
    report = synthesize(question, papers)

    os.makedirs("reports", exist_ok=True)
    timestamp = datetime.now().strftime("%Y-%m-%d_%H%M%S")
    slug = _slugify(question)
    base = f"reports/{timestamp}_curated_{slug}"

    with open(f"{base}.md", "w", encoding="utf-8") as f:
        f.write(f"# {question}\n\n> 基于 `{folder}` 目录下 {len(papers)} 篇筛选论文生成\n\n{report}")

    # 元数据
    meta = [{"title": p["title"], "source_file": p["source_file"]} for p in papers]
    with open(f"{base}_papers.json", "w", encoding="utf-8") as f:
        json.dump({"question": question, "source_folder": folder, "papers": meta},
                  f, ensure_ascii=False, indent=2)

    print(f"\n✅ 详细综述：{base}.md")
    print(f"   元数据：{base}_papers.json")


if __name__ == "__main__":
    main()
