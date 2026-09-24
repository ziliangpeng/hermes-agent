"""Behavior-contract tests for _get_usage's compact status-bar fields.

Regression for #49 (compact status bar): the usage payload exposes
`context_threshold_tokens`, `memory_tokens`/`user_tokens` (token estimate) plus
`memory_used_chars`/`memory_max_chars`/`user_used_chars`/`user_max_chars`
(char occupancy vs the STORE'S OWN limit — the M%/U% denominator), and
`skill_count`. Contracts verified (not snapshots):

- threshold: present iff the compressor exposes a positive threshold_tokens;
  equals the compressor's value (the compact bar's denominator = compression
  trigger point, not the model hard cap).
- memory/user: token fields present iff the store block is non-empty; char
  fields additionally require a positive store char limit.
- skills: counts the entries in the agent's live <available_skills> block
  (what the model sees), omitted when the agent has no skills index.
- nothing here may raise when the agent is a bare stub (fail-open contract
  shared by every other _get_usage readout).
"""
from types import SimpleNamespace

import pytest

from tui_gateway.server import _get_usage


class _StubStore:
    def __init__(self, memory_block="", user_block="", memory_char_limit=35200, user_char_limit=22000):
        self._blocks = {"memory": memory_block, "user": user_block}
        self.memory_char_limit = memory_char_limit
        self.user_char_limit = user_char_limit

    def format_for_system_prompt(self, kind):
        return self._blocks.get(kind) or ""


def _agent(**overrides):
    agent = SimpleNamespace(
        model="test-model",
        session_input_tokens=100,
        session_output_tokens=50,
        session_prompt_tokens=100,
        session_completion_tokens=50,
        session_total_tokens=150,
        session_api_calls=2,
        context_compressor=None,
        _memory_store=None,
        _memory_enabled=True,
        _user_profile_enabled=True,
        _cached_system_prompt=None,
    )
    for key, value in overrides.items():
        setattr(agent, key, value)
    return agent


class TestThresholdTokens:
    def test_present_when_compressor_has_threshold(self):
        comp = SimpleNamespace(
            last_prompt_tokens=1000, context_length=921600, threshold_tokens=783360, compression_count=0
        )
        usage = _get_usage(_agent(context_compressor=comp))
        assert usage["context_threshold_tokens"] == 783360

    def test_omitted_when_no_compressor(self):
        usage = _get_usage(_agent())
        assert "context_threshold_tokens" not in usage

    def test_omitted_when_threshold_missing_or_zero(self):
        comp = SimpleNamespace(last_prompt_tokens=1000, context_length=921600, compression_count=0)
        usage = _get_usage(_agent(context_compressor=comp))
        assert "context_threshold_tokens" not in usage
        comp2 = SimpleNamespace(
            last_prompt_tokens=1000, context_length=921600, threshold_tokens=0, compression_count=0
        )
        usage2 = _get_usage(_agent(context_compressor=comp2))
        assert "context_threshold_tokens" not in usage2


class TestMemoryUserTokens:
    def test_memory_and_user_present_when_blocks_exist(self):
        agent = _agent(_memory_store=_StubStore(memory_block="M" * 4000, user_block="U" * 2000))
        usage = _get_usage(agent)
        assert usage["memory_tokens"] > 0
        assert usage["user_tokens"] > 0
        # Same estimator as the /context breakdown: identical input → identical tokens.
        assert usage["memory_tokens"] > usage["user_tokens"]

    def test_char_occupancy_reads_against_store_limit(self):
        agent = _agent(_memory_store=_StubStore(memory_block="M" * 3520, user_block="U" * 1100))
        usage = _get_usage(agent)
        # 3,520 / 35,200 = 10% of the memory budget — visible, unlike % of a
        # 921k-token context window which rounds to zero.
        assert usage["memory_used_chars"] == 3520
        assert usage["memory_max_chars"] == 35200
        assert usage["user_used_chars"] == 1100
        assert usage["user_max_chars"] == 22000

    def test_char_fields_omitted_without_store_limit(self):
        store = _StubStore(memory_block="M" * 100, memory_char_limit=0, user_char_limit=0)
        agent = _agent(_memory_store=store)
        usage = _get_usage(agent)
        assert "memory_used_chars" not in usage
        assert "user_used_chars" not in usage
        # token estimate still present — it does not need a limit
        assert (usage.get("memory_tokens") or 0) > 0

    def test_omitted_when_store_empty(self):
        agent = _agent(_memory_store=_StubStore())
        usage = _get_usage(agent)
        assert "memory_tokens" not in usage
        assert "user_tokens" not in usage
        assert "memory_used_chars" not in usage
        assert "user_used_chars" not in usage

    def test_omitted_when_no_store(self):
        usage = _get_usage(_agent())
        assert "memory_tokens" not in usage
        assert "user_tokens" not in usage
        assert "memory_used_chars" not in usage


class TestSkillCount:
    def test_counts_index_entries(self):
        prompt = (
            "<available_skills>\n"
            "  general:\n"
            "    - alpha: does alpha things\n"
            "    - beta: does beta things\n"
            "  devops:\n"
            "    - gamma: does gamma things\n"
            "</available_skills>\n"
        )
        usage = _get_usage(_agent(_cached_system_prompt=prompt))
        assert usage["skill_count"] == 3

    def test_omitted_without_skills_block(self):
        usage = _get_usage(_agent(_cached_system_prompt="no skills here"))
        assert "skill_count" not in usage

    def test_omitted_when_block_empty(self):
        usage = _get_usage(_agent(_cached_system_prompt="<available_skills>\n\n</available_skills>"))
        assert "skill_count" not in usage


class TestFailOpen:
    def test_stub_agent_never_raises(self):
        # The whole _get_usage contract: a readout must never break usage reporting.
        usage = _get_usage(SimpleNamespace(model="x"))
        assert usage["model"] == "x"
        assert "skill_count" not in usage
