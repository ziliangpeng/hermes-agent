"""Behavior-contract tests for the gateway's ``model_alias`` wire field.

Contract (issue #48): ``session.info`` carries the SHORTEST alias configured for the
session's resolved model in the SESSION-OWNING profile's config — display-only, never
used to route. Verified behaviors, not snapshots:

- ``model.aliases:`` entries alias the model id (``custom:provider/model`` and
  ``provider/model`` values key the bare model id, which is what ``agent.model`` holds
  after a switch resolves).
- ``model_aliases:`` dict entries participate too; shortest alias wins across both.
- Provider-scoped ranking: when the route's provider is known, an alias whose provider
  prefix matches it outranks a SHORTER alias from a different provider serving the same
  model id — a staging endpoint must not lend its name to the production route.
- No matching alias → ``""`` (clients fall back to their generic label), never the
  model id echoed back.
- The lookup reads the SESSION-OWNING profile's config file, not the launch profile's:
  two profiles with different aliases for the same model id must each resolve their own
  (A→B→A under one gateway process).
- A profile home without a config.yaml fails open to ``""``.
"""
from pathlib import Path

from tui_gateway.server import _profile_reverse_alias


def _write_profile(home: Path, aliases: dict, model_aliases: dict | None = None) -> Path:
    home.mkdir(parents=True, exist_ok=True)
    lines = ["model:", "  aliases:"]
    for name, target in aliases.items():
        lines.append(f"    {name}: {target}")
    if model_aliases:
        lines.append("model_aliases:")
        for name, entry in model_aliases.items():
            lines.append(f"  {name}:")
            lines.append(f"    model: {entry['model']}")
            if "provider" in entry:
                lines.append(f"    provider: {entry['provider']}")
    (home / "config.yaml").write_text("\n".join(lines) + "\n")
    return home


class TestAliasResolution:
    def test_shortest_alias_for_model(self, tmp_path):
        home = _write_profile(tmp_path, {"longername": "custom:p1/model-x", "short": "custom:p1/model-x"})
        assert _profile_reverse_alias(str(home), "model-x") == "short"

    def test_bare_model_id_without_provider_prefix(self, tmp_path):
        home = _write_profile(tmp_path, {"m": "model-x"})
        assert _profile_reverse_alias(str(home), "model-x") == "m"

    def test_no_alias_returns_empty_not_model(self, tmp_path):
        home = _write_profile(tmp_path, {"other": "custom:p1/model-y"})
        assert _profile_reverse_alias(str(home), "model-x") == ""

    def test_model_aliases_dict_entries_count(self, tmp_path):
        home = _write_profile(tmp_path, {}, {"fromdict": {"model": "model-x", "provider": "custom"}})
        assert _profile_reverse_alias(str(home), "model-x") == "fromdict"

    def test_empty_model_name_returns_empty(self, tmp_path):
        assert _profile_reverse_alias(str(_write_profile(tmp_path, {"a": "model-x"})), "") == ""


class TestProviderScoping:
    @staticmethod
    def _two_endpoint_profile(tmp_path):
        home = tmp_path / "profile"
        home.mkdir(parents=True)
        (home / "config.yaml").write_text(
            "model:\n"
            "  aliases:\n"
            "    staging: custom:staging/model-x\n"
            "    prodname: custom:prod/model-x\n"
        )
        return home

    def test_route_provider_outranks_shorter_cross_provider_alias(self, tmp_path):
        # 'staging' (7 chars, custom:staging endpoint) would beat 'prodname' (8 chars,
        # custom:prod) on length alone; with the route's provider known, the matching
        # provider's alias must win.
        home = self._two_endpoint_profile(tmp_path)
        assert _profile_reverse_alias(str(home), "model-x", "custom:prod") == "prodname"
        assert _profile_reverse_alias(str(home), "model-x", "custom:staging") == "staging"

    def test_provider_unknown_falls_back_to_shortest(self, tmp_path):
        home = self._two_endpoint_profile(tmp_path)
        assert _profile_reverse_alias(str(home), "model-x") == "staging"
        assert _profile_reverse_alias(str(home), "model-x", "custom:other") == "staging"
        # The bare literal "custom" (agent.provider for named entries) cannot
        # discriminate either — shortest-wins is the documented fallback.
        assert _profile_reverse_alias(str(home), "model-x", "custom") == "staging"

    def test_model_aliases_dict_provider_field_ranks(self, tmp_path):
        home = _write_profile(
            tmp_path,
            {},
            {"a": {"model": "model-x", "provider": "custom:staging"},
             "b": {"model": "model-x", "provider": "custom:prod"}},
        )
        assert _profile_reverse_alias(str(home), "model-x", "custom:prod") == "b"
        assert _profile_reverse_alias(str(home), "model-x", "custom:staging") == "a"


class TestProfileIsolation:
    def test_session_profile_wins_over_launch_profile(self, tmp_path, monkeypatch):
        # The gateway process's own home (launch profile) aliases model-x differently;
        # a secondary profile's session must resolve ITS alias, not the launch one.
        launch = _write_profile(tmp_path / "launch", {"launchname": "model-x"})
        secondary = _write_profile(tmp_path / "secondary", {"secname": "model-x"})
        import tui_gateway.server as srv

        monkeypatch.setattr(srv, "_hermes_home", str(launch))
        try:
            assert _profile_reverse_alias(str(secondary), "model-x") == "secname"
            # A→B→A: resolving the secondary first must not poison the launch lookup.
            assert _profile_reverse_alias(str(launch), "model-x") == "launchname"
        finally:
            monkeypatch.undo()

    def test_missing_config_fails_open_to_empty(self, tmp_path):
        empty = tmp_path / "noconfig"
        empty.mkdir()
        assert _profile_reverse_alias(str(empty), "model-x") == ""
