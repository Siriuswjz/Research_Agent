# Research Agent

基于 DeepSeek + arXiv + Semantic Scholar 的科研文献综述 Agent，自动检索、下载、解析论文全文，生成结构化中文综述。

## 快速开始

```bash
# 1. 创建环境
conda create -n research_agent python=3.11 -y
conda activate research_agent
pip install -r requirements.txt

# 2. 配置（默认走 DeepSeek/硅基流动 + 本地代理 127.0.0.1:7897）
export DEEPSEEK_API_KEY="your-key"
export S2_API_KEY="your-key"        # 可选，没有也能跑
export HTTP_PROXY="http://127.0.0.1:7897"  # S2/PDF 下载用

# 3. 运行
python main.py
```

## 项目结构

```
research_agent/
├── main.py                          # 入口：串联四个 Agent + 报告存档
├── config.py                        # 所有配置（API key、缓存、代理、全文上限等）
├── agents/
│   ├── llm.py                       # LLM 客户端（单例 + 重试 + 缓存）
│   ├── planner.py                   # 领域识别 + 关键词拆解 + 反馈补搜
│   ├── search.py                    # 多源检索 + 去重 + Top N 全文下载
│   ├── writer.py                    # 结构化中文综述生成
│   └── critic.py                    # 审查初稿 → 修订
├── tools/
│   ├── arxiv_tool.py                # arXiv API 封装
│   ├── semantic_scholar_tool.py     # S2 API 封装
│   └── pdf_tool.py                  # PDF 下载 + PyMuPDF 解析
├── reports/                         # 生成的综述报告（按时间戳命名）
├── pdfs/                            # 下载的论文 PDF
└── .cache/                          # diskcache，7 天 TTL
```

## 已完成功能

### 核心 Pipeline
四个 Agent 串联：**Planner → Search → Writer → Critic**

| Agent | 职责 |
|---|---|
| Planner | 自动识别 8 个领域，用领域特定术语生成 2-4 个英文 query；结果不足 8 篇时反馈重搜 |
| Search | arXiv（并行）+ Semantic Scholar（限速）双源检索，按引用数排序，截断 Top 20 |
| Writer | 输出中文综述：背景 / 方法分类 / Research Gap / 参考文献 |
| Critic | 审查覆盖度、引用正确性、结构、语气，必要时让 Writer 修订 |

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

## 待改进方向

### 优先级 P0 — 马上做

**1. Semantic Scholar API key 接入**
申请下来后改 ~10 行代码：
- `config.py` 加 `S2_API_KEY = os.getenv("S2_API_KEY", "")`
- `semantic_scholar_tool.py` 有 key 时加 `x-api-key` header
- `search.py` 取消串行限制，恢复并行（速度 ×4）

### 优先级 P1 — 短期

**2. 引用图谱**
用 S2 的 `/paper/{id}/references` 和 `/citations` API：
- 拿到 Top 论文后展开引用关系
- 检测被多篇 Top 引用但自己漏掉的"奠基工作"，自动补进列表
- 工程量中等，综述完整性显著提升

**3. 闭源期刊 Cookie 复用**（针对流体顶刊）
```python
import browser_cookie3
cookies = browser_cookie3.chrome(domain_name="cambridge.org")
requests.get(jfm_pdf_url, cookies=cookies)
```
复用浏览器里登录的学校 SSO，能下 JFM / PoF / Nature 正刊。
cookie 过期需要在浏览器重新登录一次。

### 优先级 P2 — 看效果再决定

**4. PDF 解析升级 PyMuPDF → Marker**
当前 PyMuPDF 在公式、双栏、表格上质量一般。如果发现 Writer 写不出深度细节再升级 marker：
- 优点：LaTeX 公式还原、表格 markdown 化、双栏正确
- 代价：~5GB 模型权重，CPU 推理 30-60s/篇

**5. 多轮对话式精炼**
当前是一次性出报告。加交互模式后可以：
```
用户："第 3 节扩散模型部分能不能再展开 latent diffusion？"
Agent：补搜 → 重写该节
```
基于现有 Writer + Critic 改造。

### 优先级 P3 — 长期架构升级

**6. Qdrant 向量库做长期记忆**
所有搜过的论文 embed 后存向量库：
- 跨研究问题复用已下载的论文
- 真正可用的"语义级缓存"
- 支持"基于我之前读过的所有论文回答"
- 整体升级到个人科研助手

**7. LangGraph 替换手动串联**
现在 `main.py` 是顺序调用四个 Agent。换成 LangGraph 后可以：
- 显式状态机
- 条件分支（如 Critic 没过则循环最多 N 次）
- 并行节点更清晰

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
