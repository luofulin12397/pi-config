"""JWT 与鉴权相关配置。"""
from dataclasses import dataclass

from app.shared.config.common import env_float, env_str


@dataclass
class AuthConfig:
    jwt_secret_key: str
    jwt_algorithm: str
    access_token_expire_minutes: int
    refresh_token_expire_days: int
    refresh_token_remember_days: int


auth_config = AuthConfig(
    jwt_secret_key=env_str("JWT_SECRET_KEY", "change-me-in-production-use-long-random-string"),
    jwt_algorithm=env_str("JWT_ALGORITHM", "HS256"),
    access_token_expire_minutes=int(env_float("JWT_ACCESS_TOKEN_EXPIRE_MINUTES", 30)),
    refresh_token_expire_days=int(env_float("JWT_REFRESH_TOKEN_EXPIRE_DAYS", 7)),
    refresh_token_remember_days=int(env_float("JWT_REFRESH_TOKEN_REMEMBER_DAYS", 30)),
)
