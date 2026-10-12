from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import Optional


class Settings(BaseSettings):
    PROJECT_NAME: str = "AI-Based Intelligent Examination Platform"
    API_V1_STR: str = "/api/v1"
    SECRET_KEY: str = "super-secret-key-change-in-production-min-32-chars-long"
    SERVER_SECRET: str = "server-paper-generation-secret-key-change-in-prod"
    ALGORITHM: str = "HS256"

    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7
    EXAM_ACCESS_TOKEN_EXPIRE_MINUTES: int = 15
    SESSION_TOKEN_EXPIRE_MINUTES: int = 10

    RUN_SCHEDULER: bool = True
    SERVER_DEADLINE_GRACE_SECONDS: int = 3
    SESSION_SUBMIT_RETRY_MAX: int = 3

    SHORT_ANSWER_MIN_WORDS: int = 1
    SHORT_ANSWER_MAX_WORDS: int = 150
    LONG_ANSWER_MIN_WORDS: int = 1
    LONG_ANSWER_MAX_WORDS: int = 1000
    ANSWER_TEXT_MAX_CHARS: int = 10000

    ANSWER_IMAGE_MAX_SIZE_MB: int = 8
    STORAGE_BACKEND: str = "local"
    LOCAL_STORAGE_ROOT: str = "storage"

    EXAM_OBTAINED_MARKS_FLOOR: float = 0.0
    MULTI_SELECT_SCORING_STRATEGY: str = "all_or_nothing"

    LLM_PROVIDER: str = "openai"
    LLM_MODEL_NAME: str = "gpt-4o"
    LLM_API_KEY: str = ""
    LLM_TIMEOUT_SECONDS: int = 30

    DB_POOL_SIZE: int = 10
    DB_MAX_OVERFLOW: int = 20
    DB_POOL_TIMEOUT: int = 30
    DB_POOL_RECYCLE: int = 1800

    POSTGRES_SERVER: str = "localhost"
    POSTGRES_PORT: int = 5432
    POSTGRES_USER: str = "postgres"
    POSTGRES_PASSWORD: str = "postgres"
    POSTGRES_DB: str = "exam_db"
    DATABASE_URL: Optional[str] = "sqlite:///./exam_db.db"
    TEST_DATABASE_URL: Optional[str] = "sqlite:///./exam_db_test.db"

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore"
    )

    def get_database_url(self) -> str:
        if self.DATABASE_URL:
            return self.DATABASE_URL
        return f"postgresql://{self.POSTGRES_USER}:{self.POSTGRES_PASSWORD}@{self.POSTGRES_SERVER}:{self.POSTGRES_PORT}/{self.POSTGRES_DB}"


settings = Settings()
