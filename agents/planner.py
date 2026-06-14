from agents.llm import chat

# 用户常用领域 → 检索时偏好的术语 + 期刊/会议名（提高检索精度，也让 Writer 能识别顶刊）
DOMAINS = {
    "cv": "Computer Vision（CVPR, ICCV, ECCV, NeurIPS, TPAMI）",
    "nlp": "NLP（ACL, EMNLP, NAACL, NeurIPS, TACL）",
    "multimodal": "多模态（CVPR, NeurIPS, ICML, ICLR）",
    "fluid": "流体力学（JFM, Physics of Fluids, Phys. Rev. Fluids, AIAA Journal, Nature Communications）",
    "rl": "强化学习（NeurIPS, ICML, ICLR, CoRL）",
    "robotics_uav": "机器人/无人机（ICRA, IROS, RSS, CoRL, T-RO）",
    "world_model": "世界模型（NeurIPS, ICLR, ICML）",
    "general_sci": "综合科学（Nature, Nature Communications, Nature Machine Intelligence, PNAS, Science）",
}

SYSTEM = f"""你是科研任务规划专家。用户会给你一个研究问题，请：

第一行：输出领域标签（从以下选一个最匹配的，只输出小写英文标签）：
{chr(10).join(f"  - {k}: {v}" for k, v in DOMAINS.items())}

之后 2-4 行：输出英文搜索关键词组合，每行一个。要求：
- 用该领域的术语（缩写如 PINN, ViT, RLHF 可以直接用）
- 每条 query 覆盖不同角度（方法、应用、benchmark），避免雷同
- 每条 3-8 个词，便于 arXiv/Semantic Scholar 匹配

格式示例：
fluid
deep learning wall shear stress reconstruction
PINN compressible turbulent boundary layer
neural operator Navier-Stokes prediction

不要输出解释、编号、markdown。
"""

EXPAND_SYSTEM = """你是科研任务规划专家。用户之前搜索的结果太少，需要补充关键词。
请基于研究问题和已经用过的关键词，生成 2-3 个**不同角度**的新搜索词，
避免与已有关键词重复。同样每行一个，3-8 个词，不要解释。
"""


def _clean(line: str) -> str:
    line = line.strip().lstrip("-*•").strip()
    if line[:3].rstrip(".").isdigit():
        line = line.split(".", 1)[-1].strip()
    return line


def _parse_queries(text: str, min_words: int = 3) -> list[str]:
    queries, seen = [], set()
    for line in text.strip().splitlines():
        q = _clean(line)
        if len(q.split()) >= min_words and q.lower() not in seen:
            seen.add(q.lower())
            queries.append(q)
    return queries


def plan(research_question: str) -> tuple[str, list[str]]:
    """返回 (domain, queries)"""
    result = chat(SYSTEM, research_question)
    lines = [l.strip() for l in result.strip().splitlines() if l.strip()]

    # 第一行是 domain
    domain = "general_sci"
    if lines and lines[0].lower() in DOMAINS:
        domain = lines[0].lower()
        body = "\n".join(lines[1:])
    else:
        body = "\n".join(lines)

    queries = _parse_queries(body)
    if not queries:
        queries = [research_question]
    return domain, queries[:4]


def expand(research_question: str, existing_queries: list[str], domain: str) -> list[str]:
    """结果不足时，让 Planner 从其他角度补充关键词"""
    user_prompt = (
        f"研究问题：{research_question}\n"
        f"领域：{DOMAINS.get(domain, domain)}\n"
        f"已用关键词：\n" + "\n".join(f"  - {q}" for q in existing_queries)
    )
    result = chat(EXPAND_SYSTEM, user_prompt)
    new = _parse_queries(result)
    # 去掉与已有重复的
    existing_lower = {q.lower() for q in existing_queries}
    return [q for q in new if q.lower() not in existing_lower][:3]
