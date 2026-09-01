"""Tests for custom-provider scoped model specs (``custom:<provider>/<model>``).

Covers the ways a fully-qualified custom-provider model can be selected:

1. Config aliases (``model.aliases``) → ``custom:midagent/<model>`` direct
   aliases resolve in ``model_switch``.
2. Full ``custom:<provider>/<model>`` specs passed to ``-m`` /
   ``HERMES_INFERENCE_MODEL`` / ``/model`` — these must be split into
   provider + model id instead of being forwarded verbatim (which sent the
   whole spec as the model name to the default provider and 401'd through
   the proxy's Anthropic fallback).
3. ``parse_model_input`` slash-form handling, colon-form precedence, and
   model ids that themselves contain slashes or colons.
4. Provider matching by display name, provider_key, and picker slug
   (returning the canonical slug).
5. The TUI startup resolution chain and the explicit-provider escape path.
"""

import logging

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
    {
        "name": "Local Proxy",
        "provider_key": "lp",
        "base_url": "http://127.0.0.1:4141/v1",
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


@pytest.fixture(autouse=True)
def _clean_model_env(monkeypatch):
    """Keep launch-scoped model seeds out of unit tests."""
    monkeypatch.delenv("HERMES_MODEL", raising=False)
    monkeypatch.delenv("HERMES_INFERENCE_MODEL", raising=False)
    monkeypatch.delenv("HERMES_INFERENCE_PROVIDER", raising=False)
    monkeypatch.delenv("HERMES_TUI_PROVIDER", raising=False)


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

    def test_display_name_match_returns_canonical_slug(self):
        """``custom:Local Proxy/x`` resolves to the picker slug custom:local-proxy."""
        assert split_custom_provider_model_spec(
            "custom:Local Proxy/some-model", custom_providers=_MIDAGENT_CUSTOM_PROVIDERS
        ) == ("custom:local-proxy", "some-model")

    def test_slug_match(self):
        assert split_custom_provider_model_spec(
            "custom:local-proxy/some-model", custom_providers=_MIDAGENT_CUSTOM_PROVIDERS
        ) == ("custom:local-proxy", "some-model")

    def test_provider_key_match_returns_canonical_slug(self):
        """providers-dict entries carry a provider_key; matching by key still
        resolves to the canonical display-name slug the runtime uses."""
        assert split_custom_provider_model_spec(
            "custom:lp/some-model", custom_providers=_MIDAGENT_CUSTOM_PROVIDERS
        ) == ("custom:local-proxy", "some-model")

    def test_model_id_with_extra_slashes_is_preserved(self):
        assert split_custom_provider_model_spec(
            "custom:midagent/org/model", custom_providers=_MIDAGENT_CUSTOM_PROVIDERS
        ) == ("custom:midagent", "org/model")

    def test_leading_slash_model_id_is_preserved_verbatim(self):
        # Model ids are opaque strings; we do not police their shape beyond
        # non-empty.
        assert split_custom_provider_model_spec(
            "custom:midagent//model", custom_providers=_MIDAGENT_CUSTOM_PROVIDERS
        ) == ("custom:midagent", "/model")

    def test_config_load_failure_returns_none_and_logs(self, monkeypatch, caplog):
        """A config load failure must not crash, must not guess, and must not
        fail silently either."""
        def _boom(*_a, **_kw):
            raise RuntimeError("config unavailable")

        monkeypatch.setattr(
            "hermes_cli.config.get_compatible_custom_providers", _boom
        )
        with caplog.at_level(logging.WARNING, logger="hermes_cli.models"):
            result = split_custom_provider_model_spec("custom:midagent/glm-53-fp8-mi325-max")
        assert result is None
        assert any("config" in rec.message.lower() for rec in caplog.records)


class TestCustomSpecResolution:
    """Full ``custom:provider/model`` specs resolve to (provider, model)."""

    @pytest.fixture(autouse=True)
    def _midagent_provider_catalog(self, monkeypatch):
        """Point the spec splitter at the fixture config (tests run with an
        isolated HERMES_HOME, so the real user config is not visible)."""
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

    def test_colon_form_unconfigured_provider_falls_back_to_bare_custom(self):
        """Upstream strictness: an unconfigured custom:name:model spec keeps the
        model verbatim on the bare custom endpoint instead of guessing."""
        assert parse_model_input("custom:local:qwen", "openai") == ("custom", "local:qwen")

    def test_plain_model_uses_current_provider(self):
        assert parse_model_input("gpt-5.4", "openai") == ("openai", "gpt-5.4")

    def test_colon_after_slash_stays_part_of_model_id(self, _midagent_config):
        """``custom:midagent/org/model:beta``: the colon is inside the model id,
        not a provider delimiter — the scoped spec must win."""
        assert parse_model_input(
            "custom:midagent/org/model:beta", "openai"
        ) == ("custom:midagent", "org/model:beta")

    def test_colon_after_slash_unconfigured_provider_keeps_model_verbatim(self, monkeypatch):
        """``custom:edge/org/model:beta`` with no configured 'edge' provider:
        the colon-after-slash must not be treated as a delimiter either — the
        model id is preserved verbatim on the bare custom endpoint."""
        monkeypatch.setattr(
            "hermes_cli.config.get_compatible_custom_providers", lambda *_a, **_kw: []
        )
        assert parse_model_input(
            "custom:edge/org/model:beta", "openai"
        ) == ("custom", "edge/org/model:beta")

    def test_colon_before_slash_is_a_delimiter(self, _midagent_config):
        """``custom:midagent:qwen/org`` — the colon precedes the slash, so it
        is the triple-colon delimiter (validated base behavior)."""
        assert parse_model_input(
            "custom:midagent:qwen/org", "openai"
        ) == ("custom:midagent", "qwen/org")

    def test_colon_before_slash_unconfigured_falls_back_to_bare_custom(self, monkeypatch):
        """Upstream strictness: unconfigured custom:local:qwen/org keeps the
        model verbatim instead of guessing the provider."""
        assert parse_model_input(
            "custom:local:qwen/org", "openai"
        ) == ("custom", "local:qwen/org")


class TestTuiStartupResolution:
    """The TUI startup chain is a real consumer of the spec split."""

    @pytest.fixture
    def _gateway_config(self, _midagent_config, monkeypatch):
        monkeypatch.setattr("tui_gateway.server._load_cfg", lambda: _midagent_config)
        return _midagent_config

    def test_startup_seed_spec_splits(self, _gateway_config, monkeypatch):
        from tui_gateway.server import _resolve_startup_runtime

        monkeypatch.setenv("HERMES_INFERENCE_MODEL", "custom:midagent/glm-53-fp8-mi325-max")
        model, provider = _resolve_startup_runtime()
        assert model == "glm-53-fp8-mi325-max"
        assert provider == "custom:midagent"

    def test_explicit_provider_seed_keeps_model_verbatim(self, _gateway_config, monkeypatch):
        """Escape path: an explicit provider seed skips spec detection, so a
        literal model id shaped like a scoped spec is preserved verbatim."""
        from tui_gateway.server import _resolve_startup_runtime

        monkeypatch.setenv("HERMES_INFERENCE_MODEL", "custom:midagent/literal-id")
        monkeypatch.setenv("HERMES_TUI_PROVIDER", "custom:other-endpoint")
        model, provider = _resolve_startup_runtime()
        assert model == "custom:midagent/literal-id"
        assert provider == "custom:other-endpoint"


class TestSlashNamedProviders:
    """Providers whose display name itself contains a slash (legacy
    addressable via the colon triple) must keep working."""

    @pytest.fixture
    def _slash_providers(self, monkeypatch):
        providers = [
            {"name": "foo/bar", "base_url": "http://x/v1"},
        ]
        monkeypatch.setattr(
            "hermes_cli.config.get_compatible_custom_providers",
            lambda *_a, **_kw: providers,
        )
        return providers

    def test_colon_triple_resolves_slash_named_provider(self, _slash_providers):
        """custom:foo/bar:qwen with a provider literally named foo/bar."""
        assert parse_model_input("custom:foo/bar:qwen", "openai") == ("custom:foo/bar", "qwen")

    def test_unconfigured_slash_prefix_keeps_model_verbatim(self, monkeypatch):
        monkeypatch.setattr(
            "hermes_cli.config.get_compatible_custom_providers", lambda *_a, **_kw: []
        )
        assert parse_model_input("custom:foo/bar:qwen", "openai") == ("custom", "foo/bar:qwen")

    def test_scoped_spec_wins_when_both_prefixes_configured(self, monkeypatch):
        """With both foo and foo/bar configured, the scoped slash spec
        (custom:foo/...) takes precedence over the slash-named colon form."""
        providers = [
            {"name": "foo", "base_url": "http://a/v1"},
            {"name": "foo/bar", "base_url": "http://x/v1"},
        ]
        monkeypatch.setattr(
            "hermes_cli.config.get_compatible_custom_providers",
            lambda *_a, **_kw: providers,
        )
        # Scoped: the slash spec routes to provider "foo", model id "bar:qwen"
        assert parse_model_input("custom:foo/bar:qwen", "openai") == ("custom:foo", "bar:qwen")


class _RecordingAgent:
    """Minimal AIAgent stand-in: records constructor kwargs only."""

    init_kwargs: dict = {}

    def __init__(self, **kwargs):
        type(self).init_kwargs = dict(kwargs)

    def run_conversation(self, prompt):
        return {"final_response": "ok"}

    def shutdown_memory_provider(self, *_a, **_kw):
        pass

    def close(self):
        pass


class TestOneshotIntegration:
    """End-to-end through the real oneshot entry path (``hermes -z -m ...``),
    with only the AIAgent boundary replaced by a recorder. This is the path
    the original bug lived in: the spec must be split before the agent is
    constructed."""

    @pytest.fixture
    def _oneshot_env(self, monkeypatch, tmp_path):
        """Hermetic oneshot environment: a temp HERMES_HOME with a real
        config.yaml, so every layer (load_config, load_config_readonly cache,
        resolve_runtime_provider) reads the fixture config from disk instead
        of sharing process-global config caches with other tests."""
        import os as _os

        import hermes_cli.oneshot as oneshot_mod

        (tmp_path / "config.yaml").write_text(
            "custom_providers:\n"
            "  - name: midagent\n"
            "    base_url: http://localhost:19418/v1\n"
            "    key_env: VLLM_API_KEY\n"
            "    models:\n"
            "      glm-53-fp8-mi325-max: {}\n"
            "      glm-53-flash-fp8-mi350-max: {}\n"
            "model:\n"
            "  provider: custom:midagent\n"
            "  base_url: http://localhost:19418/v1\n"
            "  default: glm-53-flash-fp8-mi350\n"
            "  aliases:\n"
            "    glm53max: custom:midagent/glm-53-fp8-mi325-max\n"
            "    glm53fmax: custom:midagent/glm-53-flash-fp8-mi350-max\n"
        )
        monkeypatch.setenv("HERMES_HOME", str(tmp_path))
        monkeypatch.setattr(oneshot_mod, "_create_session_db_for_oneshot", lambda: None)
        monkeypatch.setattr(oneshot_mod, "get_fallback_chain", lambda cfg: [])
        monkeypatch.setattr("run_agent.AIAgent", _RecordingAgent)
        monkeypatch.setattr(
            "hermes_cli.tools_config._get_platform_tools", lambda cfg, platform: []
        )
        saved_env = {
            k: _os.environ.get(k)
            for k in ("HERMES_YOLO_MODE", "HERMES_ACCEPT_HOOKS")
        }
        yield oneshot_mod
        for key, value in saved_env.items():
            if value is None:
                _os.environ.pop(key, None)
            else:
                _os.environ[key] = value

    def test_m_spec_splits_before_agent_construction(self, _oneshot_env):
        import logging as _logging

        try:
            _oneshot_env.run_oneshot(
                "hi",
                model="custom:midagent/glm-53-fp8-mi325-max",
                toolsets=[],
            )
        finally:
            # run_oneshot silences logging process-wide; undo it for the
            # rest of the test session.
            _logging.disable(_logging.NOTSET)
        kwargs = _RecordingAgent.init_kwargs
        assert kwargs["model"] == "glm-53-fp8-mi325-max", kwargs
        assert kwargs["base_url"] == "http://localhost:19418/v1", kwargs
        # resolve_runtime_provider reports named custom endpoints with the
        # generic runtime label "custom" plus the explicit requested id.
        assert kwargs["requested_provider"] == "custom:midagent", kwargs
        assert kwargs["provider"] in {"custom", "custom:midagent"}, kwargs

    def test_explicit_provider_keeps_model_verbatim(self, _oneshot_env):
        import logging as _logging

        try:
            _oneshot_env.run_oneshot(
                "hi",
                model="custom:midagent/literal-id",
                provider="custom:midagent",
                toolsets=[],
            )
        finally:
            _logging.disable(_logging.NOTSET)
        kwargs = _RecordingAgent.init_kwargs
        assert kwargs["model"] == "custom:midagent/literal-id", kwargs
        assert kwargs["requested_provider"] == "custom:midagent", kwargs
        assert kwargs["base_url"] == "http://localhost:19418/v1", kwargs
