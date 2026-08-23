"""datadog_tokens — Hermes plugin for DogStatsD token-count metrics.

Emits per-API-call token counts as DogStatsD Counter metrics labeled by
model and provider. Uses non-blocking UDP to localhost:8125 (standard
DogStatsD agent port).

Activation is handled by the Hermes plugin system — standalone plugins
only load when listed in ``plugins.enabled`` (via ``hermes plugins enable
observability/datadog_tokens`` or ``hermes tools → Datadog Token Metrics``).
At runtime the plugin also requires the ``datadog`` SDK; if it is missing
the hooks are inert (fail-open).

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
  HERMES_DATADOG_TOKENS_ENABLED  — "true"/"1" to enable (checked by plugin system)
  HERMES_DATADOG_AGENT_HOST      — DogStatsD host (default: 127.0.0.1)
  HERMES_DATADOG_AGENT_PORT      — DogStatsD port (default: 8125)
"""
from __future__ import annotations

import logging
import os
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


def _env(name: str, default: str = "") -> str:
    return os.environ.get(name, default).strip()


def _env_bool(*names: str) -> bool:
    for name in names:
        value = _env(name).lower()
        if value:
            return value in {"1", "true", "yes", "on"}
    return False


def _get_client() -> Optional["DogStatsD"]:
    """Return a cached DogStatsD client, or None if unavailable.

    Thread-safe initialization. Fail-open: if the datadog SDK is missing
    or the DogStatsD agent is unreachable, all hooks silently no-op.
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
            # DogStatsD uses non-blocking UDP — no round-trip to verify.
            # The client is always "connected" from the socket side.
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

    Sanitizes values: replaces characters that DogStatsD doesn't allow
    in tag values (commas, colons in values are escaped).
    """
    tags = []
    for key in sorted(kwargs):
        value = kwargs[key]
        if not value:
            value = "unknown"
        # DogStatsD tag format: key:value
        # Replace characters that break the format
        safe_value = str(value).replace(",", "_").replace(":", "_")
        tags.append(f"{key}:{safe_value}")
    return tags


def _extract_usage(usage: Any) -> dict[str, int]:
    """Extract token counts from a usage dict or object.

    Handles both dict-style usage (from post_api_request hook) and
    objects with attributes (from raw response objects).
    """
    if usage is None:
        return {}

    if isinstance(usage, dict):
        result = {}
        for key in (
            "prompt_tokens", "completion_tokens", "total_tokens",
            "input_tokens", "output_tokens",
            "cache_read_tokens", "cache_write_tokens",
            "reasoning_tokens",
        ):
            val = usage.get(key)
            if val is not None:
                try:
                    result[key] = int(val)
                except (TypeError, ValueError):
                    pass
        # Hermes CanonicalUsage uses output_tokens, not completion_tokens.
        # Alias it so the plugin can always look up completion_tokens.
        if "completion_tokens" not in result and "output_tokens" in result:
            result["completion_tokens"] = result["output_tokens"]
        return result

    # Object with attributes (e.g. litellm.Usage)
    result = {}
    for attr in (
        "prompt_tokens", "completion_tokens", "total_tokens",
        "input_tokens", "output_tokens",
        "cache_read_tokens", "cache_write_tokens",
        "reasoning_tokens",
    ):
        val = getattr(usage, attr, None)
        if val is not None:
            try:
                result[attr] = int(val)
            except (TypeError, ValueError):
                pass
    if "completion_tokens" not in result and "output_tokens" in result:
        result["completion_tokens"] = result["output_tokens"]
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
    """
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

    # Extract token counts
    counts = _extract_usage(usage)

    try:
        # Emit token count metrics (COUNT type — Datadog auto-rollups)
        if counts.get("prompt_tokens") is not None:
            client.increment("hermes.tokens.prompt", counts["prompt_tokens"], tags=tags)
        if counts.get("completion_tokens") is not None:
            client.increment("hermes.tokens.completion", counts["completion_tokens"], tags=tags)
        if counts.get("cache_read_tokens") is not None:
            client.increment("hermes.tokens.cache_read", counts["cache_read_tokens"], tags=tags)
        if counts.get("cache_write_tokens") is not None:
            client.increment("hermes.tokens.cache_write", counts["cache_write_tokens"], tags=tags)
        if counts.get("reasoning_tokens") is not None:
            client.increment("hermes.tokens.reasoning", counts["reasoning_tokens"], tags=tags)
        if counts.get("total_tokens") is not None:
            client.increment("hermes.tokens.total", counts["total_tokens"], tags=tags)

        # Request counter (1 per API call)
        client.increment("hermes.api.calls", 1, tags=tags)

        # API duration histogram (milliseconds)
        if api_duration > 0:
            client.histogram("hermes.api.duration_ms", api_duration * 1000, tags=tags)
    except Exception as exc:  # pragma: no cover - fail-open, never block the agent
        logger.debug("Datadog token metrics: emit failed: %s", exc)


def register(ctx) -> None:
    """Register hooks for the Datadog token metrics plugin."""
    ctx.register_hook("post_api_request", on_post_api_request)
