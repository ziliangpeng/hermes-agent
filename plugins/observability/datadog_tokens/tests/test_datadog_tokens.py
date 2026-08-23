"""Tests for the Datadog token metrics plugin.

These tests do not require a running DogStatsD agent or the `datadog` SDK.
They verify:
1. Tag sanitization (no commas/colons in tag values)
2. Usage extraction from dict and object inputs
3. Fail-open behavior when SDK is missing
4. Metric emission calls the correct DogStatsD methods
"""
import pytest
import sys
import types
from unittest.mock import MagicMock, patch

# Import the plugin module
from plugins.observability.datadog_tokens import (
    _safe_tags,
    _extract_usage,
    on_post_api_request,
    _get_client,
)


class TestSafeTags:
    def test_basic_tags(self):
        tags = _safe_tags(model="gpt-4", provider="openai-api", platform="tui")
        assert "model:gpt-4" in tags
        assert "platform:tui" in tags
        assert "provider:openai-api" in tags

    def test_sorted_output(self):
        tags = _safe_tags(zebra="z", alpha="a", mango="m")
        assert tags == ["alpha:a", "mango:m", "zebra:z"]

    def test_empty_value_becomes_unknown(self):
        tags = _safe_tags(model="", provider="openai")
        assert "model:unknown" in tags
        assert "provider:openai" in tags

    def test_sanitizes_commas_and_colons(self):
        tags = _safe_tags(model="custom:midagent", provider="a,b")
        # Colons in values are replaced with _
        assert any("model:custom_midagent" == t for t in tags)
        # Commas in values are replaced with _
        assert any("provider:a_b" == t for t in tags)


class TestExtractUsage:
    def test_dict_input(self):
        usage = {
            "prompt_tokens": 100,
            "completion_tokens": 50,
            "total_tokens": 150,
            "cache_read_tokens": 80,
            "cache_write_tokens": 20,
            "reasoning_tokens": 10,
        }
        result = _extract_usage(usage)
        assert result["prompt_tokens"] == 100
        assert result["completion_tokens"] == 50
        assert result["total_tokens"] == 150
        assert result["cache_read_tokens"] == 80
        assert result["cache_write_tokens"] == 20
        assert result["reasoning_tokens"] == 10

    def test_none_input(self):
        assert _extract_usage(None) == {}

    def test_empty_dict(self):
        assert _extract_usage({}) == {}

    def test_object_input(self):
        usage_obj = types.SimpleNamespace(
            prompt_tokens=200,
            completion_tokens=100,
            total_tokens=300,
        )
        result = _extract_usage(usage_obj)
        assert result["prompt_tokens"] == 200
        assert result["completion_tokens"] == 100
        assert result["total_tokens"] == 300

    def test_invalid_values_skipped(self):
        usage = {"prompt_tokens": "not_a_number", "completion_tokens": 50}
        result = _extract_usage(usage)
        assert "prompt_tokens" not in result
        assert result["completion_tokens"] == 50


class TestOnPostApiRequest:
    def test_fail_open_when_no_client(self):
        """Plugin should silently no-op when DogStatsD client is unavailable."""
        with patch(
            "plugins.observability.datadog_tokens._get_client",
            return_value=None,
        ):
            # Should not raise
            on_post_api_request(
                model="gpt-4",
                provider="openai-api",
                platform="tui",
                usage={"prompt_tokens": 100, "completion_tokens": 50},
            )

    def test_emits_correct_metrics(self):
        """Verify the plugin calls DogStatsD with correct metric names and values."""
        mock_client = MagicMock()
        with patch(
            "plugins.observability.datadog_tokens._get_client",
            return_value=mock_client,
        ):
            on_post_api_request(
                model="gpt-4",
                provider="openai-api",
                platform="tui",
                api_duration=1.5,
                usage={
                    "prompt_tokens": 100,
                    "completion_tokens": 50,
                    "total_tokens": 150,
                    "cache_read_tokens": 80,
                    "cache_write_tokens": 20,
                    "reasoning_tokens": 10,
                },
            )

        # Verify token count metrics were emitted
        increment_calls = mock_client.increment.call_args_list
        metric_names = [call.args[0] for call in increment_calls]
        assert "hermes.tokens.prompt" in metric_names
        assert "hermes.tokens.completion" in metric_names
        assert "hermes.tokens.total" in metric_names
        assert "hermes.tokens.cache_read" in metric_names
        assert "hermes.tokens.cache_write" in metric_names
        assert "hermes.tokens.reasoning" in metric_names
        assert "hermes.api.calls" in metric_names

        # Verify duration histogram
        mock_client.histogram.assert_called_once()
        hist_call = mock_client.histogram.call_args
        assert hist_call.args[0] == "hermes.api.duration_ms"
        assert hist_call.args[1] == 1500.0  # 1.5s * 1000

    def test_prefers_response_model(self):
        """Plugin should use response_model over agent model when available."""
        mock_client = MagicMock()
        with patch(
            "plugins.observability.datadog_tokens._get_client",
            return_value=mock_client,
        ):
            on_post_api_request(
                model="gpt-4",
                provider="openai-api",
                platform="tui",
                response_model="gpt-4-0613",
                usage={"prompt_tokens": 100},
            )

        # Check that response_model was used in tags
        increment_call = mock_client.increment.call_args_list[0]
        tags = increment_call.kwargs.get("tags", [])
        assert any("model:gpt-4-0613" in t for t in tags)

    def test_no_usage_no_emit(self):
        """When usage is None, only api.calls counter should fire."""
        mock_client = MagicMock()
        with patch(
            "plugins.observability.datadog_tokens._get_client",
            return_value=mock_client,
        ):
            on_post_api_request(
                model="gpt-4",
                provider="openai-api",
                platform="tui",
                usage=None,
            )

        # Only api.calls should be emitted (no token metrics)
        increment_calls = mock_client.increment.call_args_list
        metric_names = [call.args[0] for call in increment_calls]
        assert "hermes.api.calls" in metric_names
        assert "hermes.tokens.prompt" not in metric_names

    def test_emit_exception_is_swallowed(self):
        """DogStatsD errors should never crash the agent."""
        mock_client = MagicMock()
        mock_client.increment.side_effect = Exception("UDP send failed")
        with patch(
            "plugins.observability.datadog_tokens._get_client",
            return_value=mock_client,
        ):
            # Should not raise
            on_post_api_request(
                model="gpt-4",
                provider="openai-api",
                platform="tui",
                usage={"prompt_tokens": 100},
            )
