from pydantic_settings import BaseSettings
from typing import List


class Settings(BaseSettings):
    NVIDIA_API_KEY: str
    TAVILY_API_KEY: str
    FRONTEND_URL: str = "http://localhost:5173"
    MAX_FILE_SIZE_MB: int = 10
    MAX_CLAIMS: int = 20
    MAX_SEARCH_RESULTS: int = 5
    SEARCH_TIMEOUT_SECONDS: int = 15

    CLAIM_EXTRACTION_MAX_TOKENS: int = 2048
    CLAIM_EXTRACTION_TIMEOUT_SECONDS: int = 60
    CLAIM_EXTRACTION_TEMPERATURE: float = 0.1

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


settings = Settings()
