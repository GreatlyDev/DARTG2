from __future__ import annotations

import json
import os
import random
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ANTHROPIC_MESSAGES_URL = "https://api.anthropic.com/v1/messages"
ANTHROPIC_API_VERSION = "2023-06-01"
OPENAI_RESPONSES_URL = "https://api.openai.com/v1/responses"

# Retry policy for transient HTTP / network errors.
# 429 = rate limit, 529 = Anthropic overload, 5xx = transient server errors.
RETRYABLE_HTTP_STATUSES: frozenset[int] = frozenset({408, 425, 429, 500, 502, 503, 504, 529})
MAX_RETRY_ATTEMPTS: int = 8
RETRY_BASE_DELAY_SEC: float = 1.0
RETRY_MAX_DELAY_SEC: float = 60.0


def _retry_delay(attempt: int, retry_after_sec: float | None) -> float:
    """Honor server-provided retry-after when present; otherwise exponential
    backoff with jitter, capped at RETRY_MAX_DELAY_SEC."""
    if retry_after_sec is not None and retry_after_sec > 0:
        return min(retry_after_sec, RETRY_MAX_DELAY_SEC)
    base = RETRY_BASE_DELAY_SEC * (2 ** (attempt - 1))
    return min(base + random.uniform(0, 1), RETRY_MAX_DELAY_SEC)


def _parse_retry_after(headers) -> float | None:
    if headers is None:
        return None
    value = headers.get("retry-after") or headers.get("Retry-After")
    if not value:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _post_json_with_retries(url: str, *, headers: dict, payload: dict, timeout: int,
                             label: str) -> dict[str, Any]:
    """POST a JSON payload, retrying on 429/529/5xx and network errors.
    Non-retryable 4xx errors raise RuntimeError on the first failure."""
    last_exc: Exception | None = None
    for attempt in range(1, MAX_RETRY_ATTEMPTS + 1):
        request = urllib.request.Request(
            url,
            data=json.dumps(payload).encode("utf-8"),
            headers=headers,
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                return json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            body = ""
            try:
                body = exc.read().decode("utf-8", errors="replace")
            except Exception:
                pass
            if exc.code in RETRYABLE_HTTP_STATUSES and attempt < MAX_RETRY_ATTEMPTS:
                delay = _retry_delay(attempt, _parse_retry_after(exc.headers))
                sys.stderr.write(
                    f"[retry] {label} HTTP {exc.code} (attempt {attempt}/{MAX_RETRY_ATTEMPTS}) "
                    f"— sleeping {delay:.1f}s\n"
                )
                sys.stderr.flush()
                time.sleep(delay)
                last_exc = exc
                continue
            # Non-retryable, or out of attempts.
            raise RuntimeError(
                f"{label} HTTP {exc.code} after {attempt} attempt(s): {body[:1000]}"
            ) from exc
        except urllib.error.URLError as exc:
            if attempt < MAX_RETRY_ATTEMPTS:
                delay = _retry_delay(attempt, None)
                sys.stderr.write(
                    f"[retry] {label} network error (attempt {attempt}/{MAX_RETRY_ATTEMPTS}) "
                    f"— sleeping {delay:.1f}s: {exc}\n"
                )
                sys.stderr.flush()
                time.sleep(delay)
                last_exc = exc
                continue
            raise RuntimeError(f"{label} network error after {attempt} attempts: {exc}") from exc
    raise RuntimeError(f"{label} exhausted retries: {last_exc}")


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def load_env_file(path: Path) -> None:
    if not path.exists():
        return
    for raw_line in path.read_text(encoding="utf-8-sig").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        os.environ.setdefault(key, value)


def extract_output_text(response: dict[str, Any]) -> str:
    output_text = response.get("output_text")
    if isinstance(output_text, str):
        return output_text.strip()
    chunks: list[str] = []
    for item in response.get("output", []):
        if not isinstance(item, dict):
            continue
        for content in item.get("content", []):
            if not isinstance(content, dict):
                continue
            if content.get("type") == "output_text" and isinstance(content.get("text"), str):
                chunks.append(content["text"])
    return "\n".join(chunks).strip()


def provider_for_model(model: str) -> str:
    name = model.lower()
    if name.startswith(("claude-", "claude/", "anthropic/", "anthropic-")):
        return "anthropic"
    return "openai"


class AnthropicMessagesClient:
    provider = "anthropic"

    def __init__(self, api_key: str, model: str, timeout: int = 120, max_output_tokens: int | None = None) -> None:
        self.api_key = api_key
        self.model = model
        self.timeout = timeout
        self.max_output_tokens = max_output_tokens or 1024

    def create(self, prompt: str) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "model": self.model,
            "max_tokens": self.max_output_tokens,
            "messages": [{"role": "user", "content": prompt}],
        }
        raw = _post_json_with_retries(
            ANTHROPIC_MESSAGES_URL,
            headers={
                "x-api-key": self.api_key,
                "anthropic-version": ANTHROPIC_API_VERSION,
                "Content-Type": "application/json",
            },
            payload=payload,
            timeout=self.timeout,
            label=f"anthropic[{self.model}]",
        )

        text_chunks = [
            block.get("text", "")
            for block in raw.get("content", [])
            if isinstance(block, dict) and block.get("type") == "text"
        ]
        usage = raw.get("usage", {}) or {}
        input_tokens = int(usage.get("input_tokens", 0) or 0)
        output_tokens = int(usage.get("output_tokens", 0) or 0)
        return {
            "id": raw.get("id"),
            "output_text": "\n".join(text_chunks),
            "usage": {
                "input_tokens": input_tokens,
                "output_tokens": output_tokens,
                "total_tokens": input_tokens + output_tokens,
            },
            "stop_reason": raw.get("stop_reason"),
            "provider": "anthropic",
        }


class OpenAIResponsesClient:
    provider = "openai"

    def __init__(self, api_key: str, model: str, timeout: int = 120, max_output_tokens: int | None = None) -> None:
        self.api_key = api_key
        self.model = model
        self.timeout = timeout
        self.max_output_tokens = max_output_tokens

    def create(self, prompt: str) -> dict[str, Any]:
        payload: dict[str, Any] = {"model": self.model, "input": prompt}
        if self.max_output_tokens:
            payload["max_output_tokens"] = self.max_output_tokens
        return _post_json_with_retries(
            OPENAI_RESPONSES_URL,
            headers={"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"},
            payload=payload,
            timeout=self.timeout,
            label=f"openai[{self.model}]",
        )


def make_client(model: str, openai_api_key: str | None, anthropic_api_key: str | None,
                timeout: int = 120, max_output_tokens: int | None = None):
    provider = provider_for_model(model)
    if provider == "anthropic":
        if not anthropic_api_key:
            raise SystemExit(
                f"Model {model!r} requires an Anthropic key. Add ANTHROPIC_API_KEY to .env or .anthropicapi."
            )
        return AnthropicMessagesClient(api_key=anthropic_api_key, model=model,
                                        timeout=timeout, max_output_tokens=max_output_tokens)
    if not openai_api_key:
        raise SystemExit(
            f"Model {model!r} requires an OpenAI key. Add it to .openaiapi or .env (OPENAI_API_KEY)."
        )
    return OpenAIResponsesClient(api_key=openai_api_key, model=model,
                                  timeout=timeout, max_output_tokens=max_output_tokens)
