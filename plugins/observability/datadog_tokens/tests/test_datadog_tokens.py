"""Tests for the Datadog token metrics plugin.

These tests do not require a running DogStatsD agent or the `datadog` SDK.
They verify:
1. Tag sanitization (commas, colons, pipes, newlines)
2. Usage extraction from dict and object inputs, including aliasing
3. Fail-open behavior when SDK is missing
4. Metric emission calls the correct DogStatsD methods
5. Zero-value counters are skipped
6. Exception handling throughout the hook body
"""
import pytest
import sys
import types
from unittest.mock import MagicMock, patch

from plugins.observability.datadog_tokens import (
    _safe_tags,
    _extract_usage,
    on_post_api_request,
    _get_client,
    _CLIENT_FAILED,
    _CLIENT,
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
        assert any("model:custom_midagent" == t for t in tags)
        assert any("provider:a_b" == t for t in tags)

    def test_sanitizes_pipe_and_newline(self):
        """Pipe and newline break the DogStatsD wire format."""
        tags = _safe_tags(model="model|injection", provider="line\nbreak")
        for t in tags:
            assert "|" not in t
            assert "\n" not in t
            assert "\r" not in t

    def test_sanitizes_spaces(self):
        tags = _safe_tags(model="gpt 4")
        assert any("model:gpt_4" == t for t in tags)


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

    def test_output_tokens_aliased_to_completion(self):
        """Hermes CanonicalUsage uses output_tokens, not completion_tokens."""
        usage = {"input_tokens": 100, "output_tokens": 50, "total_tokens": 150}
        result = _extract_usage(usage)
        assert result["completion_tokens"] == 50
        assert result["output_tokens"] == 50

    def test_input_tokens_aliased_to_prompt(self):
        """Hermes CanonicalUsage uses input_tokens, not prompt_tokens."""
        usage = {"input_tokens": 100, "output_tokens": 50, "total_tokens": 150}
        result = _extract_usage(usage)
        assert result["prompt_tokens"] == 100
        assert result["input_tokens"] == 100

    def test_alias_on_object_input(self):
        """Aliasing works on object attributes too."""
        usage_obj = types.SimpleNamespace(
            input_tokens=200,
            output_tokens=100,
            total_tokens=300,
        )
        result = _extract_usage(usage_obj)
        assert result["completion_tokens"] == 100
        assert result["prompt_tokens"] == 200

    def test_explicit_completion_not_overwritten(self):
        """If both completion_tokens and output_tokens exist, don't overwrite."""
        usage = {"completion_tokens": 50, "output_tokens": 999}
        result = _extract_usage(usage)
        assert result["completion_tokens"] == 50


class TestOnPostApiRequest:
    def test_fail_open_when_no_client(self):
        with patch(
            "plugins.observability.datadog_tokens._get_client",
            return_value=None,
        ):
            on_post_api_request(
                model="gpt-4",
                provider="openai-api",
                platform="tui",
                usage={"prompt_tokens": 100, "completion_tokens": 50},
            )

    def test_emits_correct_metrics(self):
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

        increment_calls = mock_client.increment.call_args_list
        metric_names = [call.args[0] for call in increment_calls]
        assert "hermes.tokens.prompt" in metric_names
        assert "hermes.tokens.completion" in metric_names
        assert "hermes.tokens.total" in metric_names
        assert "hermes.tokens.cache_read" in metric_names
        assert "hermes.tokens.cache_write" in metric_names
        assert "hermes.tokens.reasoning" in metric_names
        assert "hermes.api.calls" in metric_names

        mock_client.histogram.assert_called_once()
        hist_call = mock_client.histogram.call_args
        assert hist_call.args[0] == "hermes.api.duration_ms"
        assert hist_call.args[1] == 1500.0

    def test_prefers_response_model(self):
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

        increment_call = mock_client.increment.call_args_list[0]
        tags = increment_call.kwargs.get("tags", [])
        assert any("model:gpt-4-0613" in t for t in tags)

    def test_non_string_response_model_falls_back(self):
        """Non-string response_model should fall back to the agent model."""
        mock_client = MagicMock()
        with patch(
            "plugins.observability.datadog_tokens._get_client",
            return_value=mock_client,
        ):
            on_post_api_request(
                model="gpt-4",
                provider="openai-api",
                platform="tui",
                response_model={"unexpected": "dict"},
                usage={"prompt_tokens": 100},
            )

        increment_call = mock_client.increment.call_args_list[0]
        tags = increment_call.kwargs.get("tags", [])
        assert any("model:gpt-4" in t for t in tags)

    def test_no_usage_no_token_emit(self):
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

        increment_calls = mock_client.increment.call_args_list
        metric_names = [call.args[0] for call in increment_calls]
        assert "hermes.api.calls" in metric_names
        assert "hermes.tokens.prompt" not in metric_names

    def test_zero_value_counters_skipped(self):
        """Zero-value token counts should not emit (avoids unnecessary timeseries)."""
        mock_client = MagicMock()
        with patch(
            "plugins.observability.datadog_tokens._get_client",
            return_value=mock_client,
        ):
            on_post_api_request(
                model="gpt-4",
                provider="openai-api",
                platform="tui",
                usage={
                    "prompt_tokens": 100,
                    "completion_tokens": 0,
                    "reasoning_tokens": 0,
                },
            )

        increment_calls = mock_client.increment.call_args_list
        metric_names = [call.args[0] for call in increment_calls]
        assert "hermes.tokens.prompt" in metric_names
        assert "hermes.tokens.completion" not in metric_names
        assert "hermes.tokens.reasoning" not in metric_names
        # api.calls should still fire
        assert "hermes.api.calls" in metric_names

    def test_no_duration_no_histogram(self):
        """When api_duration is 0, no histogram should be emitted."""
        mock_client = MagicMock()
        with patch(
            "plugins.observability.datadog_tokens._get_client",
            return_value=mock_client,
        ):
            on_post_api_request(
                model="gpt-4",
                provider="openai-api",
                platform="tui",
                api_duration=0.0,
                usage={"prompt_tokens": 100},
            )

        mock_client.histogram.assert_not_called()

    def test_emit_exception_is_swallowed(self):
        """DogStatsD errors should never crash the agent."""
        mock_client = MagicMock()
        mock_client.increment.side_effect = Exception("UDP send failed")
        with patch(
            "plugins.observability.datadog_tokens._get_client",
            return_value=mock_client,
        ):
            on_post_api_request(
                model="gpt-4",
                provider="openai-api",
                platform="tui",
                usage={"prompt_tokens": 100},
            )

    def test_extraction_exception_is_swallowed(self):
        """If usage extraction raises, the hook should still not crash."""
        mock_client = MagicMock()
        with patch(
            "plugins.observability.datadog_tokens._get_client",
            return_value=mock_client,
        ), patch(
            "plugins.observability.datadog_tokens._extract_usage",
            side_effect=Exception("weird usage object"),
        ):
            on_post_api_request(
                model="gpt-4",
                provider="openai-api",
                platform="tui",
                usage=object(),
            )
