import os

from dotenv import load_dotenv

load_dotenv()

RERANK_MAX_TOPK: int = 10
RERANK_MIN_TOPK: int = 1
RERANK_GAP_RATIO: float = 0.25
RERANK_GAP_ABS: float = 0.25
RERANK_MAX_INPUT_TOKENS: int = 512
RERANK_SUMMARY_CHAR_RATIO: float = 1.3
RERANK_MIN_SUMMARY_CHARS: int = 50

RRF_FUSION_LIMIT: int = int(os.getenv("RRF_FUSION_LIMIT", "5"))
RRF_FUSION_K: int = int(os.getenv("RRF_FUSION_K", "60"))

HISTORY_COMPRESS_ENABLED: bool = os.getenv("HISTORY_COMPRESS_ENABLED", "true").lower() == "true"
HISTORY_RECENT_LIMIT: int = int(os.getenv("HISTORY_RECENT_LIMIT", "10"))
HISTORY_TOKEN_THRESHOLD: int = int(os.getenv("HISTORY_TOKEN_THRESHOLD", "3000"))
HISTORY_CHUNK_SIZE: int = int(os.getenv("HISTORY_CHUNK_SIZE", "4"))

QUERY_CACHE_ENABLED: bool = os.getenv("QUERY_CACHE_ENABLED", "true").lower() == "true"
QUERY_CACHE_TTL_SECONDS: int = int(os.getenv("QUERY_CACHE_TTL_SECONDS", "900"))

# 是否启用历史上下文压缩（false 时始终只透传近 N 条原文，不调 LLM）
HISTORY_COMPRESS_ENABLED: bool = os.getenv("HISTORY_COMPRESS_ENABLED", "true").lower() == "true"

# 滑动窗口大小：Prompt 中始终保留最近 N 条有效历史原文；更早内容靠 session_summary 摘要承载
HISTORY_RECENT_LIMIT: int = int(os.getenv("HISTORY_RECENT_LIMIT", "10"))

# 有效历史总 token 估算值超过此阈值时触发 LLM 压缩；设为 0 表示不按 token 触发，仅按条数/chunk 判断
HISTORY_TOKEN_THRESHOLD: int = int(os.getenv("HISTORY_TOKEN_THRESHOLD", "3000"))

# 自上次压缩边界（last_compressed_msg_id）之后新增消息数达到此值时，触发增量压缩更新摘要
HISTORY_CHUNK_SIZE: int = int(os.getenv("HISTORY_CHUNK_SIZE", "4"))