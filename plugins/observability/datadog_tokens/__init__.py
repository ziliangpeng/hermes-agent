"""datadog_tokens — Hermes plugin for DogStatsD token-count metrics.

Emits per-API-call token counts as DogStatsD Counter metrics labeled by
model and provider. Uses non-blocking UDP to localhost:8125 (standard
DogStatsD agent port).

Activation: enable via ``hermes plugins enable observability/datadog_tokens``
or ``hermes tools → Datadog Token Metrics``. The plugin also requires the
``datadog`` SDK (``pip install datadog``); if missing, hooks are inert.

Metrics emitted (all COUNT type, Datadog auto-rollups by time window):

  hermes.tokens.prompt          — input prompt tokens per API call
  hermes.tokens.completion      — output completion tokens per API call
  hermes.tokens.cache_read      — cache-read tokens (cached prefix replay)
  hermes.tokens.cache_write     — cache-write tokens (new prefix cached)
  hermes.tokens.reasoning       — reasoning/thinking tokens
  hermes.tokens.total           — total tokens (prompt + completion)
  hermes.api.calls              — 1 per API call (request counter)
  hermes.api.duration_ms        — API call duration in milliseconds (HISTOGRAM)

All metrics tagged with:
  model        — the model that served the request (response.model preferred)
  provider     — the provider string (openai-api, anthropic, custom:midagent, etc.)
  platform     — the Hermes platform (tui, gateway, cron, etc.)

Optional env vars:
  HERMES_DATADOG_AGENT_HOST      — DogStatsD host (default: 127.0.0.1)
  HERMES_DATADOG_AGENT_PORT      — DogStatsD port (default: 8125)
"""
from __future__ import annotations

import logging
import os
import re
import threading
from typing import Any, Optional

logger = logging.getLogger(__name__)

try:
    from datadog import DogStatsd as DogStatsD
except Exception:  # pragma: no cover - fail-open when optional dep is missing
    DogStatsD = None

_CLIENT_LOCK = threading.Lock()
_CLIENT: Optional["DogStatsD"] = None
_CLIENT_FAILED = False

_TAG_SANITIZE_RE = re.compile(r"[|,: \n\r]")

_USAGE_KEYS = (
    "prompt_tokens", "completion_tokens", "total_tokens",
    "input_tokens", "output_tokens",
    "cache_read_tokens", "cache_write_tokens",
    "reasoning_tokens",
)


def _env(name: str, default: str = "") -> str:
    return os.environ.get(name, default).strip()


def _get_client() -> Optional["DogStatsD"]:
    """Return a cached DogStatsD client, or None if unavailable.

    Thread-safe initialization. Fail-open: if the datadog SDK is missing
    or the DogStatsD agent is unreachable, all hooks silently no-op.
    Once init fails, the client is permanently disabled for the process.
    """
    global _CLIENT, _CLIENT_FAILED

    if _CLIENT_FAILED:
        return None
    if _CLIENT is not None:
        return _CLIENT

    with _CLIENT_LOCK:
        if _CLIENT_FAILED:
            return None
        if _CLIENT is not None:
            return _CLIENT

        if DogStatsD is None:
            logger.debug(
                "Datadog token metrics: datadog SDK unavailable; "
                "metrics disabled. Run `pip install datadog` to enable."
            )
            _CLIENT_FAILED = True
            return None

        host = _env("HERMES_DATADOG_AGENT_HOST", "127.0.0.1")
        port_str = _env("HERMES_DATADOG_AGENT_PORT", "8125")
        try:
            port = int(port_str)
        except ValueError:
            port = 8125

        try:
            _CLIENT = DogStatsD(host=host, port=port)
            logger.debug(
                "Datadog token metrics: DogStatsD client initialized "
                "(host=%s, port=%d)", host, port,
            )
        except Exception as exc:  # pragma: no cover - fail-open
            logger.warning(
                "Datadog token metrics: could not initialize DogStatsD "
                "client (host=%s, port=%d): %s", host, port, exc,
            )
            _CLIENT_FAILED = True
            return None

        return _CLIENT


def _safe_tags(**kwargs: Any) -> list[str]:
    """Build a sorted list of Datadog tags from keyword arguments.

    Sanitizes values: replaces characters that break the DogStatsD wire
    format (pipe, comma, colon, space, newline, carriage return).
    """
    tags = []
    for key in sorted(kwargs):
        value = kwargs[key]
        if not value:
            value = "unknown"
        safe_value = _TAG_SANITIZE_RE.sub("_", str(value))
        tags.append(f"{key}:{safe_value}")
    return tags


def _extract_usage(usage: Any) -> dict[str, int]:
    """Extract token counts from a usage dict or object.

    Handles both dict-style usage (from post_api_request hook) and
    objects with attributes (from raw response objects).

    Hermes ``CanonicalUsage`` uses ``output_tokens``/``input_tokens`` rather
    than ``completion_tokens``/``prompt_tokens``. We alias both directions
    so callers can always look up either name.
    """
    if usage is None:
        return {}

    if isinstance(usage, dict):
        result: dict[str, int] = {}
        for key in _USAGE_KEYS:
            val = usage.get(key)
            if val is not None:
                try:
                    result[key] = int(val)
                except (TypeError, ValueError):
                    pass
    else:
        # Object with attributes (e.g. litellm.Usage)
        result = {}
        for attr in _USAGE_KEYS:
            val = getattr(usage, attr, None)
            if val is not None:
                try:
                    result[attr] = int(val)
                except (TypeError, ValueError):
                    pass

    # Bi-directional aliasing: Hermes CanonicalUsage uses input/output,
    # OpenAI uses prompt/completion. Make both available.
    if "completion_tokens" not in result and "output_tokens" in result:
        result["completion_tokens"] = result["output_tokens"]
    if "prompt_tokens" not in result and "input_tokens" in result:
        result["prompt_tokens"] = result["input_tokens"]

    return result


def on_post_api_request(
    *,
    task_id: str = "",
    session_id: str = "",
    platform: str = "",
    model: str = "",
    provider: str = "",
    base_url: str = "",
    api_mode: str = "",
    api_call_count: int = 0,
    api_duration: float = 0.0,
    started_at: float = 0.0,
    ended_at: float = 0.0,
    finish_reason: str = "",
    message_count: int = 0,
    response_model: Any = None,
    response: Any = None,
    usage: Any = None,
    assistant_content_chars: int = 0,
    assistant_tool_call_count: int = 0,
    moa_references: Any = None,
    turn_id: str = "",
    api_request_id: str = "",
    **_: Any,
) -> None:
    """Emit token-count Counter metrics for each API call.

    Called by Hermes after every LLM API call (successful or not).
    Uses the ``usage`` summary dict which contains canonical token counts
    after normalization by ``agent.usage_pricing.normalize_usage``.

    The entire hook body is wrapped in a try/except so that no failure
    in tag building, usage extraction, or DogStatsD emission can ever
    block or crash the agent.
    """
    try:
        client = _get_client()
        if client is None:
            return

        # Prefer the model that actually served the request (response echoes it)
        effective_model = model
        if isinstance(response_model, str) and response_model:
            effective_model = response_model

        tags = _safe_tags(
            model=effective_model,
            provider=provider,
            platform=platform,
        )

        counts = _extract_usage(usage)

        # Emit token count metrics (COUNT type — Datadog auto-rollups).
        # Skip zero-value counters to avoid creating unnecessary timeseries.
        if counts.get("prompt_tokens"):
            client.increment("hermes.tokens.prompt", counts["prompt_tokens"], tags=tags)
        if counts.get("completion_tokens"):
            client.increment("hermes.tokens.completion", counts["completion_tokens"], tags=tags)
        if counts.get("cache_read_tokens"):
            client.increment("hermes.tokens.cache_read", counts["cache_read_tokens"], tags=tags)
        if counts.get("cache_write_tokens"):
            client.increment("hermes.tokens.cache_write", counts["cache_write_tokens"], tags=tags)
        if counts.get("reasoning_tokens"):
            client.increment("hermes.tokens.reasoning", counts["reasoning_tokens"], tags=tags)
        if counts.get("total_tokens"):
            client.increment("hermes.tokens.total", counts["total_tokens"], tags=tags)

        # Request counter (1 per API call)
        client.increment("hermes.api.calls", 1, tags=tags)

        # API duration histogram (milliseconds)
        if api_duration > 0:
            client.histogram("hermes.api.duration_ms", api_duration * 1000, tags=tags)
    except Exception as exc:  # pragma: no cover - fail-open, never block the agent
        logger.debug("Datadog token metrics: hook failed: %s", exc)


def register(ctx) -> None:
    """Register hooks for the Datadog token metrics plugin."""
    ctx.register_hook("post_api_request", on_post_api_request)
