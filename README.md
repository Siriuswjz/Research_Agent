# Research Agent

基于 DeepSeek + arXiv + Semantic Scholar 的科研助手：
- **综述模式**：给定研究问题，自动检索、下载、解析论文，生成结构化中文综述
- **精读模式**：对单篇论文做 6 节深度分析（背景/方法/实验/结果/局限/可借鉴点）

## 安装

```bash
# 推荐：从 GitHub 直装
pip install git+https://github.com/Siriuswjz/Research_Agent.git

# 或者 clone 后开发模式
git clone https://github.com/Siriuswjz/Research_Agent.git
cd Research_Agent
pip install -e .                       # 加 ".[marker]" 启用 marker 高质量解析
```

API key 申请：[硅基流动](https://cloud.siliconflow.cn/)（DeepSeek 兼容 OpenAI 接口）

### 配置 API key（任选一种）

**方式 A：`.env` 文件**（推荐，一次设置永久生效）
在你的工作目录建一个 `.env`（或全局放 `~/.research_agent.env`）：
```
DEEPSEEK_API_KEY=sk-你的key
```
完整模板见 [.env.example](.env.example)。

**方式 B：环境变量**
```bash
export DEEPSEEK_API_KEY="sk-你的key"
```

### 运行
```bash
research-agent                          # 生成综述
research-agent-read                     # 精读单篇（交互选择）
```

可选配置：`S2_API_KEY`（Semantic Scholar 提速）、`HTTP_PROXY`（代理）、`PARALLEL_WORKERS`（GPU 并行）。

### 精读模式

```bash
research-agent-read                            # 列出所有调研过的论文（跨综述去重）
research-agent-read 7                          # 单篇：全局编号
research-agent-read 1 3 5                      # 批量：多个编号
research-agent-read 1-10                       # 批量：范围
research-agent-read --latest                   # 最近一次综述里未精读的全部
research-agent-read --unread                   # pdfs/ 里未精读的全部（含手动放入的）
research-agent-read --all                      # pdfs/ + 所有综述里的全部论文，强制重读
research-agent-read --force 7                  # 强制重读指定的
research-agent-read "vision transformer"       # 标题模糊匹配
research-agent-read 2301.12345                 # arxiv ID
research-agent-read https://...                # 任意 PDF URL
research-agent-read ./paper.pdf                # 本地 PDF
research-agent-read 7 "vit" 2301.x ./p.pdf     # 混合
```

批量模式失败自动跳过，结尾汇总成功/失败，失败列表写到 `readings/_batch_<ts>_failed.md`。

默认用 PyMuPDF 解析。要更高质量装 marker：`pip install marker-pdf`（首次跑下 ~5GB 模型）。

**自动 GPU 加速**：检测到 ≥2 张 GPU 时批量精读自动多卡并行，每篇分配到不同卡上。可用环境变量 `PARALLEL_WORKERS` 强制覆盖（`disabled` / 整数 / `auto`）。

## 项目结构

```
Research_Agent/
├── pyproject.toml                   # 包元数据 + 入口命令
├── src/research_agent/
│   ├── main.py                      # 综述入口（research-agent）
│   ├── read.py                      # 精读入口（research-agent-read）
│   ├── config.py                    # 所有配置（API key、缓存、代理等）
│   ├── agents/
│   │   ├── llm.py                   # LLM 客户端（单例 + 重试 + 缓存）
│   │   ├── planner.py               # 领域识别 + 关键词拆解 + 反馈补搜
│   │   ├── search.py                # 多源检索 + 去重 + Top N 全文下载
│   │   ├── writer.py                # 结构化中文综述生成
│   │   ├── critic.py                # 审查初稿 → 修订
│   │   └── deep_reader.py           # 单篇论文 6 节深度分析
│   └── tools/
│       ├── arxiv_tool.py            # arXiv API 封装
│       ├── semantic_scholar_tool.py # S2 API 封装
│       ├── pdf_tool.py              # PDF 下载 + PyMuPDF 解析
│       ├── marker_tool.py           # marker 高质量解析（带 PyMuPDF fallback）
│       └── gpu_utils.py             # GPU 检测 + 并行 worker 推断
└── (运行时在用户当前目录创建)
    ├── reports/                     # 综述报告 + 论文元数据 JSON
    ├── readings/                    # 精读报告
    ├── pdfs/                        # 下载的论文 PDF
    └── .cache/                      # diskcache，7 天 TTL
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
