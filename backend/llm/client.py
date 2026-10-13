"""OpenRouter client with structured output, repair retries, and bounded fan-out.

Both authoring scripts (`classify`, `paths`) had their own copy of this logic.
The identical parts live here so there is one place to fix them.

Two retry kinds, deliberately distinguished:

- **Transport** — 429 and 5xx. Same request, after a backoff. The provider was
  busy, not wrong.
- **Repair** — the provider answered, but the content was unusable (it invented a
  slug, or returned no usable field). Retrying the identical request tends to fail
  identically, so the rejection reason is appended to the conversation and the
  model gets a chance to correct itself. This is the improvement over the
  TypeScript, which retried blindly.

Async because the API is: `generation` in Phase 6 streams from this provider
inside a request handler, and a blocking client there would be wrong.

Everything here costs money and needs the network, which is why the package is
separate from `rag/`: that boundary should be visible in the tree.
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
# json_schema. Not every OpenRouter route honours structured output, so the
# tolerant path is a safety net rather than dead code.
_FENCED_JSON_RE = re.compile(r"```(?:json)?\s*([\s\S]*?)```", re.IGNORECASE)

# Enough of the previous answer for the model to see what it got wrong, without
# resending a whole essay back as input.
_REPAIR_EXCERPT_CHARS = 1200


class LLMError(Exception):
    """Any failure talking to the provider, or a response we cannot use."""


class RetryableLLMError(LLMError):
    """429 or 5xx — the provider was busy. Worth the identical request again."""


class InvalidResponseError(LLMError):
    """The provider answered, but the content failed validation.

    Separate from `LLMError` because the remedy is different: the request is
    correct, so retrying needs to tell the model what was wrong.
    """


def extract_json(text: str) -> Any:
    """Pull a JSON object out of a model response.

    Accepts a markdown fence, and otherwise slices from the first `{` to the last
    `}`, so a leading sentence or trailing explanation does not break it.
    """
    fenced = _FENCED_JSON_RE.search(text)
    raw = fenced.group(1) if fenced else text
    start = raw.find("{")
    end = raw.rfind("}")
    if start < 0 or end < 0:
        raise InvalidResponseError("no JSON object in response")
    try:
        return json.loads(raw[start : end + 1])
    except json.JSONDecodeError as exc:
        raise InvalidResponseError(f"malformed JSON in response: {exc}") from exc


def collapse_whitespace(value: str) -> str:
    """Trim and collapse runs of whitespace. Applied to every free-text field."""
    return re.sub(r"\s+", " ", value).strip()


def pick_allowed(raw: Any, allowed: set[str]) -> tuple[list[str], list[str]]:
    """Split a model-supplied list into allowed values and rejected ones.

    Returns `(kept, rejected)`. Input order is preserved and duplicates dropped,
    because order carries meaning — the reader's stage chips key off the first
    phase. The rejected list exists so the caller can tell the model precisely
    what it got wrong instead of asking it to guess.
    """
    kept: list[str] = []
    rejected: list[str] = []
    if isinstance(raw, list):
        for value in raw:
            if not isinstance(value, str):
                continue
            if value in allowed:
                if value not in kept:
                    kept.append(value)
            elif value not in rejected:
                rejected.append(value)
    return kept, rejected


Validator = Callable[[Any], Any]


class OpenRouterClient:
    """Structured-output chat client.

    `chat_json` is the whole surface: give it a prompt, a JSON schema, and
    optionally a validator, and get back a value the validator accepted.
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
        self.timeout = timeout or settings.openrouter_timeout_s

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
        validate: Validator | None = None,
    ) -> Any:
        """One structured completion, retried until it is usable.

        Transport failures back off and resend. Validation failures resend with
        the rejection appended, so the model can fix the specific problem.
        """
        if not self.api_key:
            raise LLMError("OPENROUTER_API_KEY is not set")

        messages: list[dict[str, str]] = [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ]
        last_error: LLMError = LLMError("unreachable")
        raw_content = ""

        for attempt in range(1, self.max_attempts + 1):
            last = attempt == self.max_attempts
            try:
                parsed, raw_content = await self._once(
                    messages=messages,
                    schema=schema,
                    schema_name=schema_name,
                    app_title=app_title,
                    client=client,
                )
                return validate(parsed) if validate else parsed
            except RetryableLLMError as exc:
                last_error = exc
                if last:
                    break
                delay = attempt * 1.5  # matches the TypeScript: 1.5s, then 3s
                log.warning("llm.retry", attempt=attempt, delay_s=delay, error=str(exc)[:200])
                await asyncio.sleep(delay)
            except InvalidResponseError as exc:
                last_error = exc
                if last:
                    break
                log.warning("llm.repair", attempt=attempt, reason=str(exc)[:200])
                messages.append({"role": "assistant", "content": _excerpt(raw_content)})
                messages.append({"role": "user", "content": _repair_instruction(exc)})
            except LLMError as exc:
                # Non-retryable: a 4xx would fail identically every time.
                last_error = exc
                break

        raise last_error

    async def _once(
        self,
        *,
        messages: list[dict[str, str]],
        schema: dict[str, Any],
        schema_name: str,
        app_title: str,
        client: httpx.AsyncClient,
    ) -> tuple[Any, str]:
        """One request. Returns the parsed object and the raw content.

        The raw content is returned rather than stored on the instance: a repair
        retry needs it, and one client serves many concurrent requests, so
        instance state would be shared between them.
        """
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
                "messages": messages,
                "response_format": {
                    "type": "json_schema",
                    "json_schema": {"name": schema_name, "strict": True, "schema": schema},
                },
            },
            timeout=self.timeout,
        )

        if response.status_code >= 400:
            message = f"HTTP {response.status_code}: {response.text[:300]}"
            if response.status_code == 429 or response.status_code >= 500:
                raise RetryableLLMError(message)
            raise LLMError(message)

        payload = response.json()
        try:
            content = payload["choices"][0]["message"]["content"] or ""
        except (KeyError, IndexError, TypeError) as exc:
            raise RetryableLLMError(f"unexpected response shape: {str(payload)[:200]}") from exc

        return extract_json(content), content


def _excerpt(content: str) -> str:
    if len(content) <= _REPAIR_EXCERPT_CHARS:
        return content
    return content[:_REPAIR_EXCERPT_CHARS] + "…"


def _repair_instruction(error: Exception) -> str:
    """What to tell the model when its answer was rejected.

    Naming the specific problem is the point: "try again" produces the same
    mistake, while "these ids do not exist" usually does not.
    """
    return (
        f"That response was rejected: {error}. "
        "Return the same JSON shape, corrected. Use only the allowed values given "
        "above, and do not invent new ones."
    )


async def map_bounded[T](
    items: Sequence[T],
    fn: Callable[[T], Awaitable[Any]],
    *,
    concurrency: int,
) -> list[tuple[T, Any, Exception | None]]:
    """Run `fn` over `items` with at most `concurrency` in flight.

    Returns `(item, result, error)` triples rather than raising, because callers
    want to report per-item failures and keep going: one bad essay out of 233
    must not lose the other 232.
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
    "InvalidResponseError",
    "LLMError",
    "OpenRouterClient",
    "RetryableLLMError",
    "collapse_whitespace",
    "extract_json",
    "map_bounded",
    "pick_allowed",
]
