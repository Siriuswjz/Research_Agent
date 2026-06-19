from research_agent.agents.llm import chat
from research_agent.references.writing_guide import WRITING_GUIDE

SYSTEM = """你是一个科研综述撰写专家。
根据提供的论文列表，生成一份结构化的中文综述，包含：
1. 领域背景（2-3句）
2. 主要方法分类及代表工作（带引用编号 [n]）
3. 现有方法的局限性 / Research Gap
4. 参考文献列表（保留链接）

""" + WRITING_GUIDE + """

引用策略：
- 优先引用被引次数高的工作作为该方向的"代表性研究"
- 顶级期刊/会议（Nature、Nature Communications、JFM、PRL、ICML、NeurIPS 等）的论文应明确标注来源
- 近 2 年的新工作即使被引少，也要作为"最新进展"提及
- 如果某篇论文提供了"全文摘录"，可以引用其中具体的方法细节、数据、结论；
  如果只有"摘要"，引用时仅描述高层观点
- 只有当论文元数据里**明确出现** "⚠️ 闭源，需手动下载" 字样时，才将其放入文末"延伸阅读"小节；
  没有这个标记的论文**绝不要**自行判定为闭源（arXiv、NeurIPS、CVPR、Nature Communications 等都是开源的）；
  如果一篇论文都没有闭源标记，就**不要**生成"延伸阅读"小节
- 参考文献条目格式：[n] 作者. 标题. 期刊/会议, 年份. 链接

写作风格：学术严谨，简洁直接，适合作为论文 Related Work 初稿。
"""


def write(research_question: str, formatted_papers: str) -> str:
    """根据论文内容生成综述"""
    user_prompt = (
        f"研究问题：{research_question}\n\n"
        f"以下是检索到的相关论文：\n{formatted_papers}"
    )
    return chat(SYSTEM, user_prompt)
