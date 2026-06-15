# Roadmap

## ✅ 已完成

- **单篇精读模式** `read.py`：6 节结构化分析（背景/方法/实验/结果/局限/可借鉴点），支持综述编号 / arxiv ID / URL / 本地 PDF / 交互选择 5 种输入
- **marker 高质量 PDF 解析**：精读管线装了 marker 就自动用，没装 fallback PyMuPDF
- **综述论文元数据持久化** `reports/<ts>_papers.json`：供 `read.py` 索引精读

## P0 — 马上做

### 1. Semantic Scholar API key 接入
申请下来后改 ~10 行代码：
- `config.py` 加 `S2_API_KEY = os.getenv("S2_API_KEY", "")`
- `semantic_scholar_tool.py` 有 key 时加 `x-api-key` header
- `search.py` 取消串行限制，恢复并行（速度 ×4）

## P1 — 短期

### 2. 引用图谱
用 S2 的 `/paper/{id}/references` 和 `/citations` API：
- 拿到 Top 论文后展开引用关系
- 检测被多篇 Top 引用但自己漏掉的"奠基工作"，自动补进列表
- 工程量中等，综述完整性显著提升

### 3. 闭源期刊 Cookie 复用（针对流体顶刊）
```python
import browser_cookie3
cookies = browser_cookie3.chrome(domain_name="cambridge.org")
requests.get(jfm_pdf_url, cookies=cookies)
```
复用浏览器里登录的学校 SSO，能下 JFM / PoF / Nature 正刊。
cookie 过期需要在浏览器重新登录一次。

## P2 — 看效果再决定

### 4. 综述管线也用 marker
当前综述管线仍用 PyMuPDF（快、批量），如果发现 Writer 写不出深度细节再切 marker。
精读已是 marker，可参考 `tools/marker_tool.py`。

### 5. 多轮对话式精炼
当前是一次性出报告。加交互模式后可以：
```
用户："第 3 节扩散模型部分能不能再展开 latent diffusion？"
Agent：补搜 → 重写该节
```
基于现有 Writer + Critic 改造。

## P3 — 长期架构升级

### 6. Qdrant 向量库做长期记忆
所有搜过的论文 embed 后存向量库：
- 跨研究问题复用已下载的论文
- 真正可用的"语义级缓存"
- 支持"基于我之前读过的所有论文回答"
- 整体升级到个人科研助手

### 7. LangGraph 替换手动串联
现在 `main.py` 是顺序调用四个 Agent。换成 LangGraph 后可以：
- 显式状态机
- 条件分支（如 Critic 没过则循环最多 N 次）
- 并行节点更清晰
