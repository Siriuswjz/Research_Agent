import os
from pathlib import Path

# 自动加载 .env（按优先级：当前目录 > 用户主目录）
# 用户既可以 export 环境变量，也可以在工作目录或 ~/.research_agent.env 写配置
try:
    from dotenv import load_dotenv
    for env_path in [Path.cwd() / ".env", Path.home() / ".research_agent.env"]:
        if env_path.exists():
            load_dotenv(env_path, override=False)
except ImportError:
    pass

DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY", "")
DEEPSEEK_BASE_URL = "https://api.siliconflow.cn/v1"
DEEPSEEK_MODEL = "deepseek-ai/DeepSeek-V4-Pro"

MAX_SEARCH_RESULTS = 5      # 单个 query、单个源的检索上限
MAX_TOTAL_PAPERS = 20       # 喂给 Writer 的论文总量上限（按引用数排序后截断）
MIN_PAPERS = 8              # 少于这个数量就触发 Planner 补搜
MAX_TOKENS = 8192

# 缓存
CACHE_DIR = ".cache"
CACHE_TTL_SECONDS = 7 * 24 * 3600   # 7 天

# 全文管线
ENABLE_FULLTEXT = True              # 是否对开源论文下载并解析全文
FULLTEXT_TOP_N = 5                  # 引用数 Top N 篇尝试下全文
FULLTEXT_MAX_CHARS = 8000           # 单篇全文截断字符数（控制 prompt 长度）
PDF_DIR = "pdfs"

# 批量精读并行
# - "auto"（默认）：检测到 ≥2 张 GPU 自动并行，否则串行
# - "disabled"：强制串行
# - 整数：强制使用 N 个 worker
PARALLEL_WORKERS = os.getenv("PARALLEL_WORKERS", "auto")

# 代理（Semantic Scholar、arXiv PDF 下载会用）
HTTP_PROXY = os.getenv("HTTP_PROXY", "")    # 用户没设就不走代理
PROXIES = {"http": HTTP_PROXY, "https": HTTP_PROXY} if HTTP_PROXY else None
