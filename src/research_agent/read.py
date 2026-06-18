"""
精读论文：单篇或批量。

用法：
    research-agent-read                    # 交互列表（跨所有综述去重）
    research-agent-read 7                  # 全局编号
    research-agent-read 1 3 5              # 批量：多个编号
    research-agent-read 1-10               # 批量：范围
    research-agent-read --latest           # 最近一次综述里未精读的全部
    research-agent-read --unread           # pdfs/ 里未精读的全部（含手动放入的）
    research-agent-read --all              # pdfs/ + 所有综述里的全部论文，强制重读
    research-agent-read "vision transformer"  # 标题模糊匹配
    research-agent-read 2301.12345         # arxiv ID
    research-agent-read https://...        # PDF URL
    research-agent-read ./paper.pdf        # 本地 PDF
    research-agent-read --force 7          # 强制重读指定的
    可混合：research-agent-read 7 "vit" 2301.12345 ./x.pdf
"""
import os
import re
import sys
import json
import glob
import hashlib
from datetime import datetime

from research_agent.tools.pdf_tool import download_pdf
from research_agent.tools.marker_tool import parse_pdf_high_quality, is_marker_available
from research_agent.tools.gpu_utils import recommended_workers, describe_device, pick_free_gpus
from research_agent.agents.deep_reader import deep_read
from research_agent.config import PDF_DIR, PARALLEL_WORKERS


# ───────────────────────── 工具函数 ─────────────────────────

def _slugify(s: str, max_len: int = 60) -> str:
    s = re.sub(r"[^\w\s-]", "", s.lower())
    s = re.sub(r"[\s_-]+", "-", s).strip("-")
    return s[:max_len] or "untitled"


def _is_arxiv_id(s: str) -> bool:
    return bool(re.fullmatch(r"\d{4}\.\d{4,5}(v\d+)?", s))


def _arxiv_id_to_pdf(arxiv_id: str) -> str:
    return f"https://arxiv.org/pdf/{arxiv_id}.pdf"


# ───────────────────────── 全局论文索引 ─────────────────────────

def _load_all_papers() -> list[dict]:
    """
    扫所有 reports/*_papers.json，合并去重（按 URL），按时间倒序。
    返回的每条多带 _source 字段（来自哪个综述）。
    """
    files = sorted(glob.glob("reports/*_papers.json"), reverse=True)
    seen, merged = set(), []
    for fp in files:
        try:
            with open(fp, encoding="utf-8") as f:
                data = json.load(f)
        except Exception:
            continue
        # 从文件名提取综述信息
        basename = os.path.basename(fp).replace("_papers.json", "")
        question = data.get("question", "")[:40]
        source = f"{basename[:10]} {question}"
        for p in data.get("papers", []):
            url = p.get("url")
            if url and url not in seen:
                seen.add(url)
                p = dict(p)
                p["_source"] = source
                merged.append(p)
    return merged


def _scan_all_local_pdfs() -> list[str]:
    """扫 PDF_DIR 下所有 .pdf 路径，不过滤"""
    if not os.path.isdir(PDF_DIR):
        return []
    return [
        os.path.join(PDF_DIR, fname)
        for fname in sorted(os.listdir(PDF_DIR))
        if fname.lower().endswith(".pdf")
    ]


def _scan_unread_pdfs() -> list[str]:
    """扫 PDF_DIR 下所有 .pdf，过滤掉 readings/_index.json 里已记录的（按内容 hash）"""
    idx = _load_index()
    indexed_hashes = {k for k in idx if k.startswith("sha256:")}
    unread: list[str] = []
    for path in _scan_all_local_pdfs():
        h = hashlib.sha256()
        with open(path, "rb") as f:
            for chunk in iter(lambda: f.read(8192), b""):
                h.update(chunk)
        if f"sha256:{h.hexdigest()}" in indexed_hashes:
            continue
        unread.append(path)
    return unread


def _latest_papers() -> list[dict]:
    """只读最近一次综述的论文（用于 --top / --all）"""
    files = sorted(glob.glob("reports/*_papers.json"))
    if not files:
        return []
    with open(files[-1], encoding="utf-8") as f:
        return json.load(f).get("papers", [])


def _fuzzy_match(query: str, papers: list[dict]) -> list[dict]:
    """标题模糊匹配（子串、不区分大小写）"""
    q = query.lower()
    return [p for p in papers if q in p.get("title", "").lower()]


def _print_list(papers: list[dict]):
    for i, p in enumerate(papers, 1):
        flag = " ⚠️" if p.get("needs_manual") else ""
        meta_parts = []
        if p.get("venue"):
            meta_parts.append(p["venue"])
        if p.get("citation_count") is not None:
            meta_parts.append(f"被引 {p['citation_count']}")
        if p.get("_source"):
            meta_parts.append(f"来自 {p['_source']}")
        meta = " | ".join(meta_parts)
        print(f"[{i:2d}]{flag} {p['title'][:75]}")
        if meta:
            print(f"     {meta}")


# ───────────────────────── 选择器解析 ─────────────────────────

def parse_selectors(args: list[str], all_papers: list[dict]) -> list[dict | str]:
    """
    把命令行参数解析为待精读项的列表。
    每项要么是 dict（来自全局列表的 paper 元数据），要么是 str（arxiv id / url / 本地路径）
    """
    items: list[dict | str] = []

    for arg in args:
        # --unread：扫 pdfs/，加入所有未精读的 PDF
        if arg == "--unread":
            items.extend(_scan_unread_pdfs())
            continue

        # --latest：最近一次综述里所有论文（已读的会在 deep_read_one 里被跳过）
        if arg == "--latest":
            items.extend(_latest_papers())
            continue

        # --all：pdfs/ 里全部 + 所有综述里的全部论文。强制重读由 main() 中的 force 处理
        if arg == "--all":
            items.extend(_scan_all_local_pdfs())
            items.extend(all_papers)   # all_papers 已是跨综述去重的全集
            continue

        # 范围 "1-10"
        m = re.fullmatch(r"(\d+)-(\d+)", arg)
        if m:
            start, end = int(m.group(1)), int(m.group(2))
            for idx in range(start, end + 1):
                if 1 <= idx <= len(all_papers):
                    items.append(all_papers[idx - 1])
                else:
                    print(f"⚠️  编号 {idx} 超出范围（共 {len(all_papers)} 篇），跳过")
            continue

        # 纯数字 → 全局编号
        if arg.isdigit():
            idx = int(arg)
            if 1 <= idx <= len(all_papers):
                items.append(all_papers[idx - 1])
            else:
                print(f"❌ 编号 {idx} 超出范围（共 {len(all_papers)} 篇）")
            continue

        # 本地文件
        if os.path.isfile(arg) and arg.lower().endswith(".pdf"):
            items.append(arg)
            continue

        # 看起来像路径但文件不存在 → 直接报错（不去模糊匹配）
        if arg.lower().endswith(".pdf") or "/" in arg or "\\" in arg:
            print(f"❌ 文件不存在：{arg}")
            print(f"   提示：路径含空格时记得加引号，例如：")
            print(f'   research-agent-read "path with spaces/paper.pdf"')
            continue

        # arxiv ID
        if _is_arxiv_id(arg):
            items.append(arg)
            continue

        # URL
        if arg.startswith("http"):
            items.append(arg)
            continue

        # 模糊匹配标题
        matches = _fuzzy_match(arg, all_papers)
        if not matches:
            print(f"❌ 找不到匹配 '{arg}' 的论文")
            continue
        if len(matches) == 1:
            items.append(matches[0])
            continue
        # 多个匹配，要求选择
        print(f"\n🔍 '{arg}' 匹配到多篇：")
        _print_list(matches)
        choice = input("选择编号（1-{}）：".format(len(matches))).strip()
        if choice.isdigit() and 1 <= int(choice) <= len(matches):
            items.append(matches[int(choice) - 1])
        else:
            print(f"❌ 跳过 '{arg}'")

    return items


# ───────────────────────── PDF 获取 ─────────────────────────

def _download_to_local(url: str, title: str = "") -> str | None:
    os.makedirs(PDF_DIR, exist_ok=True)
    key = hashlib.md5(url.encode()).hexdigest()[:8]
    filename = f"{_slugify(title)}_{key}.pdf" if title else f"{key}.pdf"
    path = os.path.join(PDF_DIR, filename)

    if os.path.exists(path):
        return path

    print(f"   📥 下载 {url[:70]}...")
    content = download_pdf(url)
    if content is None:
        return None
    with open(path, "wb") as f:
        f.write(content)
    return path


def resolve_to_pdf(item: dict | str) -> tuple[str | None, dict | None]:
    """
    把一项解析为 (pdf_path, paper_meta)。失败返回 (None, paper_meta)。
    """
    if isinstance(item, str):
        # 本地路径
        if os.path.isfile(item) and item.lower().endswith(".pdf"):
            return item, None
        # arxiv ID
        if _is_arxiv_id(item):
            url = _arxiv_id_to_pdf(item)
            return _download_to_local(url, title=f"arxiv_{item}"), None
        # URL
        if item.startswith("http"):
            m = re.match(r"https?://arxiv\.org/abs/([\d.]+)", item)
            url = _arxiv_id_to_pdf(m.group(1)) if m else item
            return _download_to_local(url, title=hashlib.md5(item.encode()).hexdigest()[:8]), None
        return None, None

    # paper 元数据
    paper = item
    if paper.get("needs_manual"):
        return None, paper
    pdf_url = paper.get("pdf_url")
    if not pdf_url:
        return None, paper
    return _download_to_local(pdf_url, title=paper.get("title", "")), paper


# ───────────────────────── 精读索引（去重） ─────────────────────────

READINGS_INDEX = "readings/_index.json"


def _file_sha256(pdf_path: str) -> str:
    h = hashlib.sha256()
    with open(pdf_path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()


def _paper_keys(pdf_path: str, paper_meta: dict | None) -> list[str]:
    """同一篇可能在 index 里以多个 key 存在（URL + 内容 hash），保证任意入口都能识别。"""
    keys: list[str] = []
    if paper_meta and paper_meta.get("url"):
        keys.append(f"url:{paper_meta['url']}")
    keys.append(f"sha256:{_file_sha256(pdf_path)}")
    return keys


def _load_index() -> dict:
    if not os.path.exists(READINGS_INDEX):
        return {}
    try:
        with open(READINGS_INDEX, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def _save_index(idx: dict) -> None:
    os.makedirs("readings", exist_ok=True)
    with open(READINGS_INDEX, "w", encoding="utf-8") as f:
        json.dump(idx, f, ensure_ascii=False, indent=2)


# ───────────────────────── 精读 + 保存 ─────────────────────────

def deep_read_one(pdf_path: str, title: str, paper_meta: dict | None,
                  force: bool = False) -> str | None:
    """解析 + 精读 + 保存。返回精读报告路径。
    若已存在精读且 force=False，跳过并返回已有路径。"""
    keys = _paper_keys(pdf_path, paper_meta)
    idx = _load_index()
    if not force:
        for k in keys:
            if k in idx:
                existing = idx[k]["reading_path"]
                if os.path.exists(existing):
                    print(f"   ⏭  已精读过，跳过：{existing}")
                    print(f"      （加 --force 可强制重读）")
                    return existing

    print(f"   🧠 解析 PDF...")
    text = parse_pdf_high_quality(pdf_path)
    if not text.strip():
        print(f"   ❌ PDF 解析为空")
        return None
    print(f"   ✍️  DeepReader 精读中（全文 {len(text)} 字符）...")
    report = deep_read(text, paper_title=title)

    os.makedirs("readings", exist_ok=True)
    timestamp = datetime.now().strftime("%Y-%m-%d_%H%M%S")
    slug = _slugify(title)
    out_path = f"readings/{timestamp}_{slug}.md"
    with open(out_path, "w", encoding="utf-8") as f:
        header = f"> 源文件：{pdf_path}\n"
        if paper_meta:
            header += f"> 链接：{paper_meta.get('url', '')}\n"
        f.write(header + "\n" + report)

    # 注册到索引：同一篇用 URL key + SHA256 key 双写，任何入口都能识别
    entry = {"reading_path": out_path, "title": title, "date": timestamp}
    for k in keys:
        idx[k] = entry
    _save_index(idx)

    return out_path


def _parallel_worker(args):
    """multiprocessing 子进程入口：绑定指定 GPU 后跑单篇精读"""
    item, gpu_id, force = args
    if gpu_id is not None:
        os.environ["CUDA_VISIBLE_DEVICES"] = str(gpu_id)
    # 子进程要重新 import（避免父进程的 torch 已初始化导致绑卡无效）
    from research_agent.read import resolve_to_pdf, deep_read_one  # noqa
    title = item.get("title", "")[:75] if isinstance(item, dict) else str(item)
    pid = os.getpid()
    print(f"   🟢 [PID {pid}, GPU {gpu_id}] 开始：{title[:60]}", flush=True)
    try:
        pdf_path, paper_meta = resolve_to_pdf(item)
        if pdf_path is None:
            reason = "闭源，需手动下载" if (paper_meta and paper_meta.get("needs_manual")) else "PDF 下载失败"
            return ("failed", title, reason, None)
        out = deep_read_one(pdf_path, title or os.path.basename(pdf_path), paper_meta, force=force)
        return ("succeeded", title, None, out) if out else ("failed", title, "解析或精读失败", None)
    except Exception as e:
        return ("failed", title, f"{type(e).__name__}: {e}", None)


# ───────────────────────── 主流程 ─────────────────────────

def main():
    print(f"📖 PDF 解析器：{'marker (高质量)' if is_marker_available() else 'PyMuPDF (快速)'}")
    all_papers = _load_all_papers()

    args = sys.argv[1:]
    force = "--force" in args or "--all" in args   # --all 强制重读
    if "--force" in args:
        args = [a for a in args if a != "--force"]

    # 无参数 → 交互列表
    if not args:
        if not all_papers:
            print("❌ 没有任何综述报告，请先 python main.py")
            sys.exit(1)
        print(f"\n📋 共 {len(all_papers)} 篇论文（跨所有综述去重）：\n")
        _print_list(all_papers)
        choice = input("\n要精读哪些？支持单个/多个/范围（如 7 / 1 3 5 / 1-10）：").strip().split()
        if not choice:
            sys.exit(0)
        args = choice

    # 解析所有选择器
    items = parse_selectors(args, all_papers)
    if not items:
        print("❌ 没有可精读的项")
        sys.exit(1)

    # 去重（同一篇可能多次出现）
    seen, unique_items = set(), []
    for it in items:
        key = it["url"] if isinstance(it, dict) else it
        if key not in seen:
            seen.add(key)
            unique_items.append(it)

    total = len(unique_items)
    workers = recommended_workers(total, PARALLEL_WORKERS)
    # 挑出最空闲的 GPU（避开显存被占用的）
    free_gpus = pick_free_gpus(workers) if workers >= 1 else []

    # 关键：串行模式下必须在 torch 被 import 前设 env（marker 加载会触发 torch）
    # 并行模式下子进程自己在 worker 内设，父进程这里不动
    if workers <= 1 and free_gpus:
        os.environ["CUDA_VISIBLE_DEVICES"] = str(free_gpus[0])

    print(f"💻 设备：{describe_device()}")
    if free_gpus:
        print(f"🎯 使用 GPU：{free_gpus}")
    print(f"🚀 准备精读 {total} 篇（并行 worker：{workers}）\n")

    succeeded: list[str] = []
    failed: list[tuple[str, str]] = []  # (title, reason)

    if workers <= 1:
        # 串行（env 已在 describe_device 之前设过）
        for i, item in enumerate(unique_items, 1):
            title = item.get("title", "")[:75] if isinstance(item, dict) else str(item)
            print(f"\n[{i}/{total}] {title}")
            pdf_path, paper_meta = resolve_to_pdf(item)
            if pdf_path is None:
                reason = "闭源，需手动下载" if (paper_meta and paper_meta.get("needs_manual")) else "PDF 下载失败"
                print(f"   ⚠️  跳过：{reason}")
                failed.append((title, reason))
                continue
            out = deep_read_one(pdf_path, title or os.path.basename(pdf_path), paper_meta, force=force)
            if out:
                print(f"   ✅ {out}")
                succeeded.append(out)
            else:
                failed.append((title, "解析或精读失败"))
    else:
        # 多 GPU 并行（每个 worker 绑一张卡）
        # marker / surya 内部也用 multiprocessing，所以 worker 不能是 daemon
        import multiprocessing as mp
        from concurrent.futures import ProcessPoolExecutor, as_completed

        ctx = mp.get_context("spawn")
        # 把任务平均分到挑出来的空闲 GPU 上（轮转）
        tasks = [(item, free_gpus[i % len(free_gpus)], force) for i, item in enumerate(unique_items)]
        # ProcessPoolExecutor 的 worker 不是 daemon，子进程可以再开子进程
        with ProcessPoolExecutor(max_workers=workers, mp_context=ctx) as pool:
            futures = [pool.submit(_parallel_worker, t) for t in tasks]
            for i, future in enumerate(as_completed(futures), 1):
                result = future.result()
                status, title, reason, out = result
                if status == "succeeded":
                    print(f"[{i}/{total}] ✅ {title}\n            → {out}")
                    succeeded.append(out)
                else:
                    print(f"[{i}/{total}] ⚠️  {title}\n            → {reason}")
                    failed.append((title, reason))

    # 汇总
    print(f"\n{'=' * 60}")
    print(f"✅ 成功 {len(succeeded)} / 失败 {len(failed)}")
    if failed:
        print(f"\n失败论文：")
        for title, reason in failed:
            print(f"  - [{reason}] {title}")
        # 写失败汇总到 readings/
        os.makedirs("readings", exist_ok=True)
        ts = datetime.now().strftime("%Y-%m-%d_%H%M%S")
        fail_path = f"readings/_batch_{ts}_failed.md"
        with open(fail_path, "w", encoding="utf-8") as f:
            f.write("# 批量精读失败汇总\n\n")
            for title, reason in failed:
                f.write(f"- **{reason}**: {title}\n")
        print(f"\n失败汇总：{fail_path}")


if __name__ == "__main__":
    main()
