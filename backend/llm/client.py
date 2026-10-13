"""OpenRouter client with structured output, retries and bounded concurrency.

Both authoring scripts (`classify`, `paths`) had their own copy of this logic.
The parts that were identical — `extract_json`, the retry policy, the request
shape, the header set — live here so there is one place to fix them.

This is async because the API is: `generation` in Phase 6 streams from the same
provider inside a request handler, and a blocking client there would be wrong.

Everything here costs money and needs the network, which is why the package is
separate from `rag/`: that boundary is visible in the tree on purpose.
"""

import asyncio
import json
import re
from collections.abc import Awaitable, Callable, Sequence
from typing import Any

import httpx

from config import settings
from core.logging_config import log

# Models occasionally wrap JSON in a markdown fence even when asked for
# json_schema, so the fenced form has to be accepted.
_FENCED_JSON_RE = re.compile(r"```(?:json)?\s*([\s\S]*?)```", re.IGNORECASE)

_REQUEST_TIMEOUT_S = 120.0


class LLMError(Exception):
    """Any failure talking to the provider, or a response we cannot use."""


class RetryableLLMError(LLMError):
    """429 or 5xx — worth another attempt."""


def extract_json(text: str) -> Any:
    """Pull a JSON object out of a model response.

    Accepts a markdown fence, and otherwise slices from the first `{` to the
    last `}` so a leading sentence or trailing explanation does not break it.
    """
    fenced = _FENCED_JSON_RE.search(text)
    raw = fenced.group(1) if fenced else text
    start = raw.find("{")
    end = raw.rfind("}")
    if start < 0 or end < 0:
        raise LLMError("no JSON object in response")
    try:
        return json.loads(raw[start : end + 1])
    except json.JSONDecodeError as exc:
        raise LLMError(f"malformed JSON in response: {exc}") from exc


def collapse_whitespace(value: str) -> str:
    """Trim and collapse runs of whitespace. Applied to every free-text field."""
    return re.sub(r"\s+", " ", value).strip()


class OpenRouterClient:
    """Structured-output chat client.

    `chat_json` is the whole surface: give it a prompt and a JSON schema, get
    back a dict that conforms to it. Validation of *semantics* (are these real
    slugs?) belongs to the caller, not here.
    """

    def __init__(
        self,
        *,
        api_key: str | None = None,
        base_url: str | None = None,
        model: str | None = None,
        max_attempts: int | None = None,
        timeout: float | None = None,
    ) -> None:
        self.api_key = api_key if api_key is not None else settings.openrouter_api_key
        self.base_url = (base_url or settings.openrouter_base_url).rstrip("/")
        self.model = model or settings.openrouter_model
        self.max_attempts = max_attempts or settings.llm_max_attempts
        self.timeout = timeout or settings.openrouter_timeout_s or _REQUEST_TIMEOUT_S

    @property
    def configured(self) -> bool:
        return bool(self.api_key)

    async def chat_json(
        self,
        *,
        system: str,
        user: str,
        schema: dict[str, Any],
        schema_name: str,
        app_title: str,
        client: httpx.AsyncClient,
    ) -> Any:
        """One structured completion, with the retry policy applied.

        Retries 429 and 5xx. A 4xx is a bug in the request and will fail the
        same way three times, so it fails fast.
        """
        last_error: LLMError = LLMError("unreachable")

        for attempt in range(1, self.max_attempts + 1):
            try:
                return await self._once(
                    system=system,
                    user=user,
                    schema=schema,
                    schema_name=schema_name,
                    app_title=app_title,
                    client=client,
                )
            except RetryableLLMError as exc:
                last_error = exc
                if attempt == self.max_attempts:
                    break
                # Matches the TypeScript backoff: 1.5s, 3s.
                delay = attempt * 1.5
                log.warning("llm.retry", attempt=attempt, delay_s=delay, error=str(exc)[:200])
                await asyncio.sleep(delay)
            except LLMError as exc:
                last_error = exc
                break

        raise last_error

    async def _once(
        self,
        *,
        system: str,
        user: str,
        schema: dict[str, Any],
        schema_name: str,
        app_title: str,
        client: httpx.AsyncClient,
    ) -> Any:
        if not self.api_key:
            raise LLMError("OPENROUTER_API_KEY is not set")

        response = await client.post(
            f"{self.base_url}/chat/completions",
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
                "HTTP-Referer": "https://askgraham.vercel.app",
                "X-Title": app_title,
            },
            json={
                "model": self.model,
                "messages": [
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
                "response_format": {
                    "type": "json_schema",
                    "json_schema": {"name": schema_name, "strict": True, "schema": schema},
                },
            },
            timeout=self.timeout,
        )

        if response.status_code >= 400:
            body = response.text[:300]
            message = f"HTTP {response.status_code}: {body}"
            if response.status_code == 429 or response.status_code >= 500:
                raise RetryableLLMError(message)
            raise LLMError(message)

        payload = response.json()
        try:
            content = payload["choices"][0]["message"]["content"] or ""
        except (KeyError, IndexError, TypeError) as exc:
            raise LLMError(f"unexpected response shape: {str(payload)[:200]}") from exc

        # A missing or unparseable body is treated as retryable: the provider
        # answered, so trying again is more likely to help than to hurt.
        try:
            return extract_json(content)
        except LLMError as exc:
            raise RetryableLLMError(str(exc)) from exc


async def map_bounded[T](
    items: Sequence[T],
    fn: Callable[[T], Awaitable[Any]],
    *,
    concurrency: int,
) -> list[tuple[T, Any, Exception | None]]:
    """Run `fn` over `items` with at most `concurrency` in flight.

    Returns `(item, result, error)` triples rather than raising, because both
    callers want to report per-item failures and keep going.
    """
    semaphore = asyncio.Semaphore(max(1, concurrency))
    results: list[tuple[T, Any, Exception | None]] = [None] * len(items)  # type: ignore[list-item]

    async def run(index: int, item: T) -> None:
        async with semaphore:
            try:
                results[index] = (item, await fn(item), None)
            except Exception as exc:
                results[index] = (item, None, exc)

    await asyncio.gather(*(run(i, item) for i, item in enumerate(items)))
    return results


__all__ = [
    "LLMError",
    "OpenRouterClient",
    "RetryableLLMError",
    "collapse_whitespace",
    "extract_json",
    "map_bounded",
]
