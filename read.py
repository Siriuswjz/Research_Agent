"""
精读单篇论文。

用法：
    python read.py                    # 交互模式：列出最近综述的论文供选择
    python read.py 7                  # 综述里的编号
    python read.py 2301.12345         # arxiv ID
    python read.py https://...        # 任意 PDF URL
    python read.py ./paper.pdf        # 本地 PDF 路径
"""
import os
import re
import sys
import json
import glob
import hashlib
from datetime import datetime

from tools.pdf_tool import download_pdf
from tools.marker_tool import parse_pdf_high_quality, is_marker_available
from agents.deep_reader import deep_read
from config import PDF_DIR


def _slugify(s: str, max_len: int = 60) -> str:
    s = re.sub(r"[^\w\s-]", "", s.lower())
    s = re.sub(r"[\s_-]+", "-", s).strip("-")
    return s[:max_len] or "untitled"


def _latest_papers_json() -> str | None:
    files = sorted(glob.glob("reports/*_papers.json"))
    return files[-1] if files else None


def _load_papers(path: str) -> list[dict]:
    with open(path, encoding="utf-8") as f:
        return json.load(f)["papers"]


def _arxiv_id_to_pdf(arxiv_id: str) -> str:
    return f"https://arxiv.org/pdf/{arxiv_id}.pdf"


def _is_arxiv_id(s: str) -> bool:
    return bool(re.fullmatch(r"\d{4}\.\d{4,5}(v\d+)?", s))


def resolve_input(arg: str | None) -> tuple[str, dict | None]:
    """
    返回 (本地 PDF 路径, 论文元数据 dict or None)
    """
    # 模式 C: 无参数 → 交互列表
    if arg is None:
        return _interactive_select()

    # 模式 B-3: 本地文件
    if os.path.isfile(arg) and arg.lower().endswith(".pdf"):
        return arg, None

    # 模式 A: 纯数字 → 综述编号
    if arg.isdigit():
        return _from_report_index(int(arg))

    # 模式 B-1: arxiv ID
    if _is_arxiv_id(arg):
        return _download_to_local(_arxiv_id_to_pdf(arg), title=f"arxiv_{arg}"), None

    # 模式 B-2: URL
    if arg.startswith("http"):
        # arxiv abs URL → 转 pdf URL
        m = re.match(r"https?://arxiv\.org/abs/([\d.]+)", arg)
        if m:
            return _download_to_local(_arxiv_id_to_pdf(m.group(1)), title=f"arxiv_{m.group(1)}"), None
        return _download_to_local(arg, title=hashlib.md5(arg.encode()).hexdigest()[:8]), None

    raise ValueError(f"无法识别的输入：{arg}")


def _interactive_select() -> tuple[str, dict]:
    latest = _latest_papers_json()
    if not latest:
        print("❌ 没有找到任何综述报告，请先 python main.py 跑一次")
        sys.exit(1)

    papers = _load_papers(latest)
    print(f"\n📋 来自 {latest}：\n")
    for i, p in enumerate(papers, 1):
        flag = " ⚠️" if p.get("needs_manual") else ""
        venue = f" | {p['venue']}" if p.get("venue") else ""
        citation = f" | 被引 {p['citation_count']}" if p.get("citation_count") is not None else ""
        print(f"[{i:2d}]{flag} {p['title'][:80]}{venue}{citation}")

    choice = input("\n要精读哪一篇？输入编号：").strip()
    if not choice.isdigit():
        print("❌ 必须是数字")
        sys.exit(1)

    idx = int(choice)
    if not (1 <= idx <= len(papers)):
        print(f"❌ 编号 {idx} 超出范围（1-{len(papers)}）")
        sys.exit(1)

    paper = papers[idx - 1]
    return _resolve_paper(paper), paper


def _from_report_index(idx: int) -> tuple[str, dict]:
    latest = _latest_papers_json()
    if not latest:
        print("❌ 没有找到任何综述报告，请先 python main.py 跑一次")
        sys.exit(1)
    papers = _load_papers(latest)
    if not (1 <= idx <= len(papers)):
        print(f"❌ 编号 {idx} 超出范围（最近综述有 {len(papers)} 篇）")
        sys.exit(1)
    paper = papers[idx - 1]
    return _resolve_paper(paper), paper


def _resolve_paper(paper: dict) -> str:
    """从 paper 元数据下载 PDF，闭源/失败则提示"""
    if paper.get("needs_manual"):
        print(f"\n⚠️  这篇是闭源论文（{paper.get('venue', '')}），需要手动下载")
        print(f"   链接：{paper['url']}")
        print(f"   下载后用：python read.py <pdf路径>")
        sys.exit(1)

    pdf_url = paper.get("pdf_url")
    if not pdf_url:
        print(f"❌ 论文没有 PDF 链接：{paper['title']}")
        sys.exit(1)

    return _download_to_local(pdf_url, title=paper["title"])


def _download_to_local(url: str, title: str = "") -> str:
    os.makedirs(PDF_DIR, exist_ok=True)
    key = hashlib.md5(url.encode()).hexdigest()[:8]
    filename = f"{_slugify(title)}_{key}.pdf" if title else f"{key}.pdf"
    path = os.path.join(PDF_DIR, filename)

    if os.path.exists(path):
        print(f"✅ 已存在本地 PDF：{path}")
        return path

    print(f"📥 下载 {url} ...")
    content = download_pdf(url)
    if content is None:
        print(f"❌ 下载失败（可能是闭源或网络问题）")
        sys.exit(1)
    with open(path, "wb") as f:
        f.write(content)
    print(f"✅ 已保存：{path}")
    return path


def main():
    arg = sys.argv[1] if len(sys.argv) > 1 else None
    print(f"📖 PDF 解析器：{'marker (高质量)' if is_marker_available() else 'PyMuPDF (快速)'}")

    pdf_path, paper_meta = resolve_input(arg)
    title = paper_meta.get("title", "") if paper_meta else os.path.basename(pdf_path)

    print(f"\n🧠 解析 PDF 全文...")
    text = parse_pdf_high_quality(pdf_path)
    if not text.strip():
        print("❌ PDF 解析为空")
        sys.exit(1)
    print(f"   共 {len(text)} 字符")

    print(f"\n✍️  DeepReader：生成精读报告...")
    report = deep_read(text, paper_title=title)

    # 保存
    os.makedirs("readings", exist_ok=True)
    timestamp = datetime.now().strftime("%Y-%m-%d_%H%M%S")
    slug = _slugify(title)
    out_path = f"readings/{timestamp}_{slug}.md"
    with open(out_path, "w", encoding="utf-8") as f:
        header = f"> 源文件：{pdf_path}\n"
        if paper_meta:
            header += f"> 链接：{paper_meta.get('url', '')}\n"
        f.write(header + "\n" + report)

    print(f"\n✅ 精读报告：{out_path}")


if __name__ == "__main__":
    main()
