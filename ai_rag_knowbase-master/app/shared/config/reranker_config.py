"""
Reranker 配置模块，负责读取重排模型相关环境变量。
"""
from dataclasses import dataclass

from app.shared.config.common import env_bool, env_str

@dataclass
class RerankerConfig:
    bge_reranker_large: str
    bge_reranker_device: str
    bge_reranker_fp16: bool
    # API 化（M1 联调）：走 /rerank 端点（硅基流动 bge-reranker-v2-m3）
    api_base: str = ""
    api_key: str = ""
    api_model: str = "BAAI/bge-reranker-v2-m3"

reranker_config = RerankerConfig(
    bge_reranker_large=env_str("BGE_RERANKER_LARGE"),
    bge_reranker_device=env_str("BGE_RERANKER_DEVICE"),
    bge_reranker_fp16=env_bool("BGE_RERANKER_FP16"),
    api_base=env_str("RERANK_API_BASE", ""),
    api_key=env_str("RERANK_API_KEY", ""),
    api_model=env_str("RERANK_MODEL", "BAAI/bge-reranker-v2-m3"),
)
