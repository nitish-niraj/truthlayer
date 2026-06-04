from openai import OpenAI
from .config import settings

_client = None

MODEL_NAME = "moonshotai/kimi-k2.6"
BASE_URL = "https://integrate.api.nvidia.com/v1"

DEFAULT_TEMPERATURE = 1.0
DEFAULT_TOP_P = 1.0
DEFAULT_MAX_TOKENS = 16384
THINKING_ENABLED = True


def get_llm_client() -> OpenAI:
    global _client
    if _client is None:
        _client = OpenAI(base_url=BASE_URL, api_key=settings.NVIDIA_API_KEY)
    return _client
