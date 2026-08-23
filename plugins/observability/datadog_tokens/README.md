# Datadog Token Metrics Plugin

Emits per-API-call token counts as DogStatsD Counter metrics labeled by model and provider.

## Metrics

All metrics are COUNT type (Datadog auto-rollups by time window) unless noted:

| Metric | Type | Description |
|--------|------|-------------|
| `hermes.tokens.prompt` | COUNT | Input prompt tokens per API call |
| `hermes.tokens.completion` | COUNT | Output completion tokens per API call |
| `hermes.tokens.cache_read` | COUNT | Cache-read tokens (cached prefix replay) |
| `hermes.tokens.cache_write` | COUNT | Cache-write tokens (new prefix cached) |
| `hermes.tokens.reasoning` | COUNT | Reasoning/thinking tokens |
| `hermes.tokens.total` | COUNT | Total tokens (prompt + completion) |
| `hermes.api.calls` | COUNT | 1 per API call (request counter) |
| `hermes.api.duration_ms` | HISTOGRAM | API call duration in milliseconds |

All metrics tagged with:
- `model` — the model that served the request
- `provider` — the provider string (openai-api, anthropic, custom:midagent, etc.)
- `platform` — the Hermes platform (tui, gateway, cron, etc.)

## Setup

1. Install the `datadog` Python package: `pip install datadog`
2. Ensure a Datadog Agent with DogStatsD is running on localhost:8125
3. Enable the plugin: `hermes plugins enable observability/datadog_tokens`

## Configuration

Optional env vars (set via `hermes tools` or `~/.hermes/.env`):

| Env var | Default | Description |
|---------|---------|-------------|
| `HERMES_DATADOG_TOKENS_ENABLED` | unset | Set to "true"/"1" to enable |
| `HERMES_DATADOG_AGENT_HOST` | 127.0.0.1 | DogStatsD host |
| `HERMES_DATADOG_AGENT_PORT` | 8125 | DogStatsD port |

## Fail-open behavior

If the `datadog` SDK is missing or the DogStatsD agent is unreachable, all
hooks silently no-op. The plugin will never block or crash the agent.
