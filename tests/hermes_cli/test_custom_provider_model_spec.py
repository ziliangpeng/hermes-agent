"""Tests for GLM max / flash-max model selection paths.

Covers the ways a user can select the midagent max models:

1. Config aliases (``model.aliases``) → ``custom:midagent/<model>`` direct
   aliases resolve in ``model_switch``.
2. Full ``custom:<provider>/<model>`` specs passed to ``-m`` / ``HERMES_INFERENCE_MODEL``
   / ``/model`` — these must be split into provider + model id instead of being
   forwarded verbatim (which sent the whole spec as the model name to the
   default provider and 401'd through the proxy's Anthropic fallback).
3. ``parse_model_input`` slash-form handling for ``/model`` input.
"""

import pytest

from hermes_cli.models import (
    detect_provider_for_model,
    parse_model_input,
    split_custom_provider_model_spec,
)

_MIDAGENT_CUSTOM_PROVIDERS = [
    {
        "name": "midagent",
        "base_url": "http://localhost:19418/v1",
        "key_env": "VLLM_API_KEY",
        "models": {
            "glm-53-fp8-mi325-max": {},
            "glm-53-flash-fp8-mi350-max": {},
        },
    },
]


@pytest.fixture
def _midagent_config(monkeypatch):
    """Config with the midagent custom provider and max-model aliases."""
    mock_config = {
        "custom_providers": _MIDAGENT_CUSTOM_PROVIDERS,
        "model": {
            "provider": "custom:midagent",
            "base_url": "http://localhost:19418/v1",
            "default": "glm-53-flash-fp8-mi350",
            "aliases": {
                "glm53max": "custom:midagent/glm-53-fp8-mi325-max",
                "glm53fmax": "custom:midagent/glm-53-flash-fp8-mi350-max",
            },
        },
    }
    monkeypatch.setattr("hermes_cli.config.load_config", lambda: mock_config)
    return mock_config


class TestSplitCustomProviderModelSpec:
    def test_splits_configured_provider_spec(self):
        assert split_custom_provider_model_spec(
            "custom:midagent/glm-53-fp8-mi325-max", custom_providers=_MIDAGENT_CUSTOM_PROVIDERS
        ) == ("custom:midagent", "glm-53-fp8-mi325-max")

    def test_case_insensitive_provider_name(self):
        assert split_custom_provider_model_spec(
            "custom:Midagent/glm-53-fp8-mi325-max", custom_providers=_MIDAGENT_CUSTOM_PROVIDERS
        ) == ("custom:midagent", "glm-53-fp8-mi325-max")

    def test_unknown_provider_name_is_not_split(self):
        assert (
            split_custom_provider_model_spec(
                "custom:not-a-provider/some-model", custom_providers=_MIDAGENT_CUSTOM_PROVIDERS
            )
            is None
        )

    def test_no_slash_is_not_split(self):
        assert split_custom_provider_model_spec("custom:midagent") is None

    def test_empty_model_id_is_not_split(self):
        assert split_custom_provider_model_spec("custom:midagent/", custom_providers=_MIDAGENT_CUSTOM_PROVIDERS) is None

    def test_non_custom_prefix_is_not_split(self):
        assert split_custom_provider_model_spec("openrouter/anthropic/claude-sonnet-4.5") is None

    def test_vendor_slash_model_without_configured_provider_passes_through(self, monkeypatch):
        """Bare ``custom`` endpoint with an OpenRouter-style id must stay intact."""
        monkeypatch.setattr(
            "hermes_cli.config.get_compatible_custom_providers", lambda *_a, **_kw: []
        )
        assert split_custom_provider_model_spec("custom:meta-llama/llama-4") is None


class TestCustomSpecResolution:
    """Full ``custom:provider/model`` specs resolve to (provider, model)."""

    @pytest.fixture(autouse=True)
    def _midagent_provider_catalog(self, monkeypatch):
        """Point the spec splitter at the midagent fixture config."""
        monkeypatch.setattr(
            "hermes_cli.config.get_compatible_custom_providers",
            lambda *_a, **_kw: list(_MIDAGENT_CUSTOM_PROVIDERS),
        )

    def test_detect_provider_for_full_spec(self):
        result = detect_provider_for_model(
            "custom:midagent/glm-53-fp8-mi325-max", current_provider="custom:midagent"
        )
        assert result == ("custom:midagent", "glm-53-fp8-mi325-max")

    def test_detect_provider_for_full_spec_from_other_provider(self):
        result = detect_provider_for_model(
            "custom:midagent/glm-53-flash-fp8-mi350-max", current_provider="anthropic"
        )
        assert result == ("custom:midagent", "glm-53-flash-fp8-mi350-max")

    def test_static_catalog_guard_untouched(self, monkeypatch):
        """Bare catalog names must still not hijack a custom endpoint (#48305)."""
        assert detect_provider_for_model("gpt-5.4", "custom:foo") is None


class TestAliasResolution:
    def test_config_aliases_resolve_to_max_models(self, _midagent_config, monkeypatch):
        import hermes_cli.model_switch as ms

        monkeypatch.setattr(ms, "DIRECT_ALIASES", {})
        aliases = ms._load_direct_aliases()
        assert aliases["glm53max"].provider == "custom:midagent"
        assert aliases["glm53max"].model == "glm-53-fp8-mi325-max"
        assert aliases["glm53fmax"].provider == "custom:midagent"
        assert aliases["glm53fmax"].model == "glm-53-flash-fp8-mi350-max"

    def test_alias_then_spec_are_equivalent(self, _midagent_config, monkeypatch):
        """-m glm53max and -m custom:midagent/glm-53-fp8-mi325-max resolve to the
        same (provider, model) pair."""
        import hermes_cli.model_switch as ms

        monkeypatch.setattr(ms, "DIRECT_ALIASES", {})
        direct = ms._load_direct_aliases()["glm53max"]
        spec = split_custom_provider_model_spec("custom:midagent/glm-53-fp8-mi325-max")
        assert (direct.provider, direct.model) == spec


class TestParseModelInput:
    def test_slash_form_routes_to_named_custom_provider(self, _midagent_config):
        assert parse_model_input(
            "custom:midagent/glm-53-fp8-mi325-max", "openai"
        ) == ("custom:midagent", "glm-53-fp8-mi325-max")

    def test_colon_form_still_works_for_configured_provider(self, _midagent_config):
        assert parse_model_input("custom:midagent:qwen", "openai") == ("custom:midagent", "qwen")

    def test_colon_form_unconfigured_provider(self):
        """Unconfigured custom:name:model resolves on the bare custom endpoint
        (lenient pre-validation behavior on this branch)."""
        assert parse_model_input("custom:local:qwen", "openai") == ("custom:local", "qwen")

    def test_plain_model_uses_current_provider(self):
        assert parse_model_input("gpt-5.4", "openai") == ("openai", "gpt-5.4")
