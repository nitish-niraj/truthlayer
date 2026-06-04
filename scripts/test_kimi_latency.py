"""Smoke test: verify NVIDIA/Kimi provider responsiveness and measure latency.

Usage (from repo root):
    python scripts/test_kimi_latency.py

Env:
    NVIDIA_API_KEY  (loaded from backend/.env if present, otherwise from process env)
"""
import os
import time
from pathlib import Path

from dotenv import load_dotenv
from openai import OpenAI

BASE_URL = "https://integrate.api.nvidia.com/v1"
MODEL = "moonshotai/kimi-k2.6"

load_dotenv(Path(__file__).resolve().parent.parent / "backend" / ".env")

api_key = os.getenv("NVIDIA_API_KEY")
if not api_key:
    raise SystemExit("NVIDIA_API_KEY not set (set in env or backend/.env)")

client = OpenAI(base_url=BASE_URL, api_key=api_key)
prompt = "Reply with exactly one word: hello"

start = time.perf_counter()
try:
    response = client.chat.completions.create(
        model=MODEL,
        messages=[{"role": "user", "content": prompt}],
        temperature=0.1,
        max_tokens=20,
        stream=False,
        timeout=60,
        extra_body={"chat_template_kwargs": {"thinking": False}},
    )
    elapsed = time.perf_counter() - start
    status = 200
    text = response.choices[0].message.content or ""
except Exception as exc:
    elapsed = time.perf_counter() - start
    status = getattr(exc, "status_code", 0) or 0
    text = f"ERROR: {type(exc).__name__}: {exc}"

print(f"status_code: {status}")
print(f"latency:     {elapsed:.2f}s")
print(f"response:    {text!r}")
