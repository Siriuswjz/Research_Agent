from research_agent.agents.llm import chat
from research_agent.references.writing_guide import WRITING_CHECKLIST

CRITIC_SYSTEM = """你是科研综述审稿专家。请审查给定的综述初稿，重点检查：

1. **覆盖度**：论文列表中是否有重要工作被遗漏？
2. **引用正确性**：综述里的引用编号 [n] 是否对应到正确的论文？是否引用了列表外的论文？
3. **数字/事实编造**：综述里出现的具体数字、指标、方法细节，是否有依据？
   （特别注意：如果论文列表只给了摘要或截断的全文，综述里不应该出现表格中的精确数字）
4. **结构完整性**：报告章节是否完整、有无明显缺漏？
5. **公式格式**：数学公式是否用 `$...$` / `$$...$$`？严禁 `\\[...\\]`、`\\(...\\)`、单独 `[...]`
6. **学术语气**：是否存在口语化、夸大、模糊的表述？

""" + WRITING_CHECKLIST + """

输出格式：
PASS  ← 如果没有重大问题，只输出这一个词，不要解释
或者：
- 问题1: 描述
- 问题2: 描述
（最多 6 条，每条一行）

不要输出修改后的全文，只输出问题清单。
"""

REVISE_SYSTEM = """你是科研综述撰写专家。根据 Critic 给出的问题清单，
修改综述初稿。只输出修改后的全文，不要解释改了什么。
"""


def review(formatted_papers: str, draft: str) -> str:
    """返回 Critic 的问题清单，或 'PASS'"""
    user_prompt = (
        f"== 论文列表 ==\n{formatted_papers}\n\n"
        f"== 综述初稿 ==\n{draft}"
    )
    return chat(CRITIC_SYSTEM, user_prompt)


def revise(formatted_papers: str, draft: str, issues: str) -> str:
    """根据问题清单修改综述"""
    user_prompt = (
        f"== 论文列表 ==\n{formatted_papers}\n\n"
        f"== 初稿 ==\n{draft}\n\n"
        f"== Critic 问题清单 ==\n{issues}"
    )
    return chat(REVISE_SYSTEM, user_prompt)
