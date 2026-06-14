import os

DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY", "")
DEEPSEEK_BASE_URL = "https://api.siliconflow.cn/v1"
DEEPSEEK_MODEL = "deepseek-ai/DeepSeek-V4-Pro"

MAX_SEARCH_RESULTS = 5      # 单个 query、单个源的检索上限
MAX_TOTAL_PAPERS = 20       # 喂给 Writer 的论文总量上限（按引用数排序后截断）
MIN_PAPERS = 8              # 少于这个数量就触发 Planner 补搜
MAX_TOKENS = 4096

# 缓存
CACHE_DIR = ".cache"
CACHE_TTL_SECONDS = 7 * 24 * 3600   # 7 天

# 全文管线
ENABLE_FULLTEXT = True              # 是否对开源论文下载并解析全文
FULLTEXT_TOP_N = 5                  # 引用数 Top N 篇尝试下全文
FULLTEXT_MAX_CHARS = 8000           # 单篇全文截断字符数（控制 prompt 长度）
PDF_DIR = "pdfs"

# 代理（Semantic Scholar、arXiv PDF 下载会用）
HTTP_PROXY = os.getenv("HTTP_PROXY", "http://127.0.0.1:7897")
PROXIES = {"http": HTTP_PROXY, "https": HTTP_PROXY} if HTTP_PROXY else None
