from research_agent.agents.llm import chat
from research_agent.references.writing_guide import WRITING_GUIDE

SYSTEM = """你是科研综述撰写专家。用户已经从大量文献中**筛选**出一批核心参考文献，
请基于这批论文撰写一份详细的中文综述，作为论文 Related Work / 引言 的成稿初版。

""" + WRITING_GUIDE + """

# 报告结构

## 0. 一段话总览
（150-300 字概述这批论文整体讲了什么、研究脉络的核心线索）

## 1. 研究背景
- 领域概况，为什么这个问题重要
- 当前的核心挑战
- 历史脉络（如果论文里有提到早期工作）

## 2. 研究脉络
按时间或方法演进梳理这批论文，识别 2-4 个主要研究方向。
每个方向：
- 该方向的核心思路（数学定义 / 模型架构等）
- 代表性工作及其具体贡献（引用编号 [n]）
- 方向之间的关系、互补性

## 3. 方法对比与归纳
横向对比各论文的方法、设定、性能。
**强烈建议用 Markdown 表格**，例如：

| 方法 | 任务 | 数据集 | 关键指标 | 引用 |
|---|---|---|---|---|
| ... | ... | ... | ... | [3] |

## 4. 共识与争议
- 这批论文达成了哪些共识？（如某种架构是 SOTA、某种 loss 必备）
- 还有哪些观点分歧或未解决的问题？

## 5. 研究空白与机会
基于这批论文的局限，本研究可以切入的角度。
要具体（"现有方法在 X 场景失败，可结合 Y 解决"），不要空话。

## 6. 参考文献
按引用编号列出，含标题、作者、年份、来源。

# 写作要求

- **比快速综述更长更详细**：目标 3000-5000 字（不算参考文献）
- 大量引用论文中的具体方法、数字、结论
- 用学术严谨的中文，关键术语保留英文
- 公式格式必须用 Markdown 兼容写法：
  - 行内：`$E = mc^2$`
  - 块级：`$$L = \\sum_i (y_i - \\hat{y}_i)^2$$`
  - **严禁** `\\[...\\]`、`\\(...\\)`、单独 `[...]`
- 如果某篇论文信息不完整（全文截断），明确写"全文未提供"，不要编造
"""


def synthesize(research_question: str, papers: list[dict]) -> str:
    """
    papers: list of {"title": str, "fulltext": str}
    """
    sections = []
    for i, p in enumerate(papers, 1):
        sections.append(
            f"## [{i}] {p['title']}\n\n{p['fulltext']}\n"
        )
    user_prompt = (
        f"研究问题：{research_question}\n\n"
        f"以下是 {len(papers)} 篇核心参考文献的全文摘录：\n\n"
        + "\n---\n\n".join(sections)
    )
    return chat(SYSTEM, user_prompt)
