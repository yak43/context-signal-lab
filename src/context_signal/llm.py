"""Optional one-call review adapter using only the Python standard library."""

from __future__ import annotations

import json
import os
import urllib.request

from .models import Report


def build_review_prompt(report: Report) -> str:
    # Send only fixed analyzer codes, severities and numeric metrics. Finding
    # details/evidence can contain private tool names or user-provided text.
    findings = "\n".join(f"- [{item.severity}] {item.code}" for item in report.findings[:40])
    return (
        "Review this deterministic LLM trace report. Return at most three short actions.\n"
        f"score={report.score}; estimated_tokens={report.estimated_tokens}\n{findings}"
    )


def request_review(report: Report) -> str:
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY is required for --llm")
    base_url = os.environ.get("OPENAI_BASE_URL", "https://api.openai.com/v1").rstrip("/")
    model = os.environ.get("CONTEXT_SIGNAL_MODEL", "gpt-4o-mini")
    max_tokens = int(os.environ.get("CONTEXT_SIGNAL_MAX_OUTPUT_TOKENS", "180"))
    if not 1 <= max_tokens <= 512:
        raise ValueError("Model output limit must be between 1 and 512 tokens")
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": "You are a concise LLM quality reviewer."},
            {"role": "user", "content": build_review_prompt(report)},
        ],
        "temperature": 0,
        "max_tokens": max_tokens,
    }
    request = urllib.request.Request(
        f"{base_url}/chat/completions",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        body = json.loads(response.read().decode("utf-8"))
    return str(body["choices"][0]["message"]["content"]).strip()
