from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import List


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    NVIDIA_API_KEY: str
    TAVILY_API_KEY: str
    FRONTEND_URL: str = "http://localhost:5173"
    MAX_FILE_SIZE_MB: int = 10
    MAX_IMAGE_SIZE_MB: int = 5
    MAX_CLAIMS: int = 20
    MAX_SEARCH_RESULTS: int = 5
    SEARCH_TIMEOUT_SECONDS: int = 8

    # Claim extraction (LLM #1). Tight budget so we always have time left for
    # search + verdict stages on Render's 30s free-tier wall clock.
    CLAIM_EXTRACTION_MAX_TOKENS: int = 2048
    CLAIM_EXTRACTION_TIMEOUT_SECONDS: int = 20
    CLAIM_EXTRACTION_TEMPERATURE: float = 0.1

    # Hard server-side cap for the full /api/verify pipeline. The route returns
    # whatever claims have completed when this elapses. Stays well under
    # Render's 30s free-tier proxy timeout so we always own the response.
    VERIFY_HARD_TIMEOUT_SECONDS: float = 25.0

    # Maximum characters of document text sent to the claim-extraction LLM.
    # Larger documents are truncated to keep the LLM stage predictable.
    VERIFY_MAX_INPUT_CHARS: int = 6000


settings = Settings()
