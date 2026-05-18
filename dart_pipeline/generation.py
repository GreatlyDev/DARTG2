from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable


OPENAI_RESPONSES_URL = "https://api.openai.com/v1/responses"
ANTHROPIC_MESSAGES_URL = "https://api.anthropic.com/v1/messages"
ANTHROPIC_API_VERSION = "2023-06-01"


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


def candidate_id(job: dict[str, Any]) -> str:
    return str(job.get("job_id") or f"{job['anchor_id']}_{job['dialect_family']}_{job['candidate_index']}")


def generation_input(job: dict[str, Any], total_candidates: int | None = None) -> str:
    candidate_index = int(job.get("candidate_index", 1))
    total = total_candidates or int(job.get("target_candidates", 3) or 3)
    diversity_note = (
        f"\n\nCandidate attempt: {candidate_index} of {total}.\n"
        "If more than one valid rewrite is possible, choose a natural rewrite that is not identical to the other attempts, "
        "while still following every rule above."
    )
    return f"{job['generation_prompt']}{diversity_note}"


class OpenAIResponsesClient:
    provider = "openai"

    def __init__(
        self,
        api_key: str,
        model: str,
        timeout: int = 120,
        max_output_tokens: int | None = None,
    ) -> None:
        self.api_key = api_key
        self.model = model
        self.timeout = timeout
        self.max_output_tokens = max_output_tokens

    def create(self, prompt: str) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "model": self.model,
            "input": prompt,
        }
        if self.max_output_tokens:
            payload["max_output_tokens"] = self.max_output_tokens

        request = urllib.request.Request(
            OPENAI_RESPONSES_URL,
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                return json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"OpenAI API request failed with HTTP {exc.code}: {body}") from exc
        except urllib.error.URLError as exc:
            raise RuntimeError(f"OpenAI API request failed: {exc}") from exc


class AnthropicMessagesClient:
    provider = "anthropic"

    def __init__(
        self,
        api_key: str,
        model: str,
        timeout: int = 120,
        max_output_tokens: int | None = None,
    ) -> None:
        self.api_key = api_key
        self.model = model
        self.timeout = timeout
        # Anthropic requires max_tokens; default to 1024 if caller didn't set one.
        self.max_output_tokens = max_output_tokens or 1024

    def create(self, prompt: str) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "model": self.model,
            "max_tokens": self.max_output_tokens,
            "messages": [{"role": "user", "content": prompt}],
        }
        request = urllib.request.Request(
            ANTHROPIC_MESSAGES_URL,
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "x-api-key": self.api_key,
                "anthropic-version": ANTHROPIC_API_VERSION,
                "Content-Type": "application/json",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                raw = json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"Anthropic API request failed with HTTP {exc.code}: {body}") from exc
        except urllib.error.URLError as exc:
            raise RuntimeError(f"Anthropic API request failed: {exc}") from exc

        # Normalize Anthropic's content[]/usage into the same shape OpenAI uses, so
        # extract_output_text() and downstream code don't need provider-aware paths.
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
            "raw": raw,
        }


def provider_for_model(model: str) -> str:
    """Detect which provider hosts a given model based on its ID prefix."""
    name = model.lower()
    if name.startswith(("claude-", "claude/", "anthropic/", "anthropic-")):
        return "anthropic"
    if name.startswith(("gpt-", "o1-", "o3-", "o4-", "openai/", "openai-")) or name in {"gpt-4o", "gpt-4", "gpt-3.5-turbo"}:
        return "openai"
    # Fallback: treat as OpenAI; will surface as a 4xx from the API if wrong.
    return "openai"


def make_client(
    model: str,
    openai_api_key: str | None,
    anthropic_api_key: str | None,
    timeout: int = 120,
    max_output_tokens: int | None = None,
):
    """Return the right client instance for a model. Raises SystemExit if the needed key is missing."""
    provider = provider_for_model(model)
    if provider == "anthropic":
        if not anthropic_api_key:
            raise SystemExit(
                f"Model {model!r} requires an Anthropic key. Add ANTHROPIC_API_KEY to .env "
                f"or pass --anthropic-key-file."
            )
        return AnthropicMessagesClient(
            api_key=anthropic_api_key,
            model=model,
            timeout=timeout,
            max_output_tokens=max_output_tokens,
        )
    if not openai_api_key:
        raise SystemExit(
            f"Model {model!r} requires an OpenAI key. Add it to .openaiapi or .env (OPENAI_API_KEY)."
        )
    return OpenAIResponsesClient(
        api_key=openai_api_key,
        model=model,
        timeout=timeout,
        max_output_tokens=max_output_tokens,
    )


def generate_candidate_record(
    job: dict[str, Any],
    client: OpenAIResponsesClient,
    generation_status: str,
    total_candidates: int | None = None,
) -> dict[str, Any]:
    request_input = generation_input(job, total_candidates=total_candidates)
    started_at = utc_now()
    response = client.create(request_input)
    finished_at = utc_now()
    candidate_response = extract_output_text(response)

    return {
        "candidate_id": candidate_id(job),
        "anchor_id": str(job["anchor_id"]),
        "dialect_family": str(job["dialect_family"]),
        "candidate_index": int(job["candidate_index"]),
        "prompt_version": str(job.get("prompt_version", "")),
        "model": client.model,
        "generation_status": generation_status,
        "candidate_response": candidate_response,
        "raw_output": candidate_response,
        "openai_response_id": response.get("id"),
        "usage": response.get("usage", {}),
        "started_at": started_at,
        "finished_at": finished_at,
        "source_job_id": str(job.get("job_id", "")),
    }


def existing_candidate_ids(rows: Iterable[dict[str, Any]]) -> set[str]:
    return {str(row.get("candidate_id")) for row in rows if row.get("candidate_id")}


def sleep_between_calls(seconds: float) -> None:
    if seconds > 0:
        time.sleep(seconds)
