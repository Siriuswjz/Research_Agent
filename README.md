# Research Agent

基于 DeepSeek + arXiv + Semantic Scholar 的科研助手：
- **综述模式**：给定研究问题，自动检索、下载、解析论文，生成结构化中文综述
- **精读模式**：对单篇论文做 6 节深度分析（背景/方法/实验/结果/局限/可借鉴点）

## 快速开始

```bash
conda create -n research_agent python=3.11 -y
conda activate research_agent
pip install -r requirements.txt

export DEEPSEEK_API_KEY="your-key"
python main.py                       # 生成综述
python read.py                       # 精读单篇（交互选择）
```

可选环境变量：`S2_API_KEY`（Semantic Scholar 提速）、`HTTP_PROXY`（代理）。

### 精读模式

```bash
python read.py                       # 列出所有调研过的论文（跨综述去重），选编号
python read.py 7                     # 单篇：全局编号
python read.py 1 3 5                 # 批量：多个编号
python read.py 1-10                  # 批量：范围
python read.py --top 5               # 批量：最近综述被引前 5
python read.py --all                 # 批量：最近综述全部
python read.py "vision transformer"  # 标题模糊匹配
python read.py 2301.12345            # arxiv ID
python read.py https://...           # 任意 PDF URL
python read.py ./paper.pdf           # 本地 PDF
python read.py 7 "vit" 2301.x ./p.pdf  # 混合
```

批量模式失败自动跳过，结尾汇总成功/失败，失败列表写到 `readings/_batch_<ts>_failed.md`。

默认用 PyMuPDF 解析。要更高质量装 marker：`pip install marker-pdf`（首次跑下 ~5GB 模型）。

## 项目结构

```
research_agent/
├── main.py                          # 综述入口：串联四个 Agent
├── read.py                          # 精读入口：单篇深度分析
├── config.py                        # 所有配置（API key、缓存、代理、全文上限等）
├── agents/
│   ├── llm.py                       # LLM 客户端（单例 + 重试 + 缓存）
│   ├── planner.py                   # 领域识别 + 关键词拆解 + 反馈补搜
│   ├── search.py                    # 多源检索 + 去重 + Top N 全文下载
│   ├── writer.py                    # 结构化中文综述生成
│   ├── critic.py                    # 审查初稿 → 修订
│   └── deep_reader.py               # 单篇论文 6 节深度分析
├── tools/
│   ├── arxiv_tool.py                # arXiv API 封装
│   ├── semantic_scholar_tool.py     # S2 API 封装
│   ├── pdf_tool.py                  # PDF 下载 + PyMuPDF 解析
│   └── marker_tool.py               # marker 高质量解析（带 PyMuPDF fallback）
├── reports/                         # 综述报告 + 论文元数据 JSON
├── readings/                        # 精读报告
├── pdfs/                            # 下载的论文 PDF
└── .cache/                          # diskcache，7 天 TTL
```

## 已完成功能

### 综述 Pipeline
四个 Agent 串联：**Planner → Search → Writer → Critic**

| Agent | 职责 |
|---|---|
| Planner | 自动识别 8 个领域，用领域特定术语生成 2-4 个英文 query；结果不足 8 篇时反馈重搜 |
| Search | arXiv（并行）+ Semantic Scholar（限速）双源检索，按引用数排序，截断 Top 20 |
| Writer | 输出中文综述：背景 / 方法分类 / Research Gap / 参考文献 |
| Critic | 审查覆盖度、引用正确性、结构、语气，必要时让 Writer 修订 |

### 精读 Pipeline
单 Agent：**DeepReader**，输出 6 节结构化分析（背景/方法/实验/结果/局限/可借鉴点）。
支持单篇或批量，跑多次综述后所有论文跨报告**全局去重 + 全局编号**。

输入方式见 [快速开始 → 精读模式](#精读模式)。

PDF 解析器自动选择：装了 marker 用 marker（公式/表格/双栏高质量），没装用 PyMuPDF（快速）。

### 内置领域
`cv / nlp / multimodal / fluid / rl / robotics_uav / world_model / general_sci`，每个领域配对应的顶刊/顶会名（JFM、PoF、Nature、ICML、CVPR、NeurIPS 等）。

### 全文管线
- Top 5 高被引论文自动下 PDF，`pymupdf` 解析后喂 Writer
- 开源（arXiv / NeurIPS / CVPR / Nature Communications）→ 自动全文
- 闭源（JFM / Nature 正刊）→ 标 ⚠️，放"延伸阅读"提示手动下载
- PDF 保存到 `pdfs/`，文件名按标题 slug

### 工程基础设施
- **错误处理**：指数退避重试，429 特殊处理，PDF 失败原因详细打印
- **缓存**：`diskcache` 7 天 TTL，覆盖 LLM 调用、arXiv、S2、PDF 解析文本
- **客户端单例**：复用 TCP 连接池
- **代理**：S2 API + PDF 下载走代理（DeepSeek 直连）
- **输入确认**：避免中文输入截断
- **报告存档**：`reports/<时间戳>_<问题slug>.md`

## 配置项速查

`config.py` 里可调：

| 配置 | 默认值 | 含义 |
|---|---|---|
| `MAX_SEARCH_RESULTS` | 5 | 单 query + 单源检索数 |
| `MAX_TOTAL_PAPERS` | 20 | 喂给 Writer 的论文总量上限 |
| `MIN_PAPERS` | 8 | 少于这个数量触发 Planner 补搜 |
| `ENABLE_FULLTEXT` | True | 是否对开源论文下载并解析全文 |
| `FULLTEXT_TOP_N` | 5 | 引用数 Top N 篇下全文 |
| `FULLTEXT_MAX_CHARS` | 8000 | 单篇全文截断字符数 |
| `CACHE_TTL_SECONDS` | 7×24×3600 | 缓存有效期 |
| `HTTP_PROXY` | `http://127.0.0.1:7897` | S2 + PDF 下载代理 |

## Roadmap

待改进方向和优先级见 [ROADMAP.md](ROADMAP.md)。
