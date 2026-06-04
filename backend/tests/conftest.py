import os

os.environ.setdefault("NVIDIA_API_KEY", "test-nvidia-key")
os.environ.setdefault("TAVILY_API_KEY", "test-tavily-key")
os.environ.setdefault("FRONTEND_URL", "http://localhost:5173")
os.environ.setdefault("MAX_FILE_SIZE_MB", "10")
os.environ.setdefault("MAX_CLAIMS", "20")

import pytest
from fastapi.testclient import TestClient

from main import app


@pytest.fixture
def client():
    return TestClient(app)
