"""
Polish Agent —— 综述润色。

Critic 负责"写对内容"（事实、引用、结构），Polish 负责"写得漂亮"
（段落流、claim-first、技术化对比）。两个认知任务分开做，质量更高。
"""
from research_agent.agents.llm import chat
from research_agent.references.writing_guide import WRITING_GUIDE

POLISH_SYSTEM = """你是 Nature 系期刊的资深语言编辑。请对给定的中文科研综述做**写作润色**，
让它达到顶刊 Related Work 的表达水准。

""" + WRITING_GUIDE + """

润色要求：
- **只改写表达，不改事实**：不得新增/删除引用编号，不得改动任何数字、方法名、结论
- 把按年份罗列的段落，重组为按技术主题分组的论证
- 每段改成 claim-first（首句点题），补上显式逻辑衔接词
- 把"某某也做了某事"式的罗列，改写为机制/假设/失败模式层面的对比
- 删掉空泛的过渡句和营销式措辞，让技术区别一目了然
- 保持章节结构和引用编号不变
- 公式继续用 `$...$` / `$$...$$`，严禁 `\\[...\\]`、`\\(...\\)`、单独 `[...]`

只输出润色后的完整全文，不要解释改了什么。
"""


def polish(draft: str) -> str:
    return chat(POLISH_SYSTEM, f"以下是待润色的综述全文：\n\n{draft}")
