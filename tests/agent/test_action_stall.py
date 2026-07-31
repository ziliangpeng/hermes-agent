"""Tests for agent.action_stall — action-stall detection and continuation.

Covers:
- build_action_stall_continuation() returns text with the stable prefix
- latest_user_message_is_stall_continuation() detects the stall pattern
- Returns False for non-matching patterns (assistant WITH tools, regular
  user message, empty/single messages, None/list-of-parts content, etc.)
- Edge cases: marker not in last position, previous message not assistant

Ported from upstream PR #58368, adapted to our local implementation.
"""

from agent.action_stall import (
    ACTION_STALL_CONTINUATION_PREFIX,
    build_action_stall_continuation,
    latest_user_message_is_stall_continuation,
)


# ── build_action_stall_continuation ──────────────────────────────────


class TestBuildActionStallContinuation:
    def test_returns_string_starting_with_prefix(self):
        text = build_action_stall_continuation()
        assert isinstance(text, str)
        assert text.startswith(ACTION_STALL_CONTINUATION_PREFIX)

    def test_contains_instruction_to_execute_tool_calls(self):
        text = build_action_stall_continuation()
        assert "Execute the required tool calls" in text

    def test_prefix_is_stable_constant(self):
        """The prefix is a wire-protocol marker; it must not change."""
        assert ACTION_STALL_CONTINUATION_PREFIX == (
            "[System corrective continuation: tool execution required]"
        )

    def test_build_idempotent(self):
        """Calling twice returns the same text."""
        assert build_action_stall_continuation() == build_action_stall_continuation()


# ── latest_user_message_is_stall_continuation — True cases ──────────


class TestStallContinuationDetects:
    def test_stall_after_no_tool_assistant(self):
        """Core case: assistant narrates intent but emits no tool_calls,
        conversation loop injects stall continuation as last user message.
        """
        messages = [
            {"role": "user", "content": "Inspect the repo."},
            {"role": "assistant", "content": "I'll inspect the repo now."},
            {"role": "user", "content": build_action_stall_continuation()},
        ]
        assert latest_user_message_is_stall_continuation(messages) is True

    def test_stall_with_empty_assistant_content(self):
        """Assistant content can be empty/None — the stall is about missing
        tool_calls, not missing text."""
        messages = [
            {"role": "user", "content": "Run date."},
            {"role": "assistant", "content": None},
            {"role": "user", "content": build_action_stall_continuation()},
        ]
        assert latest_user_message_is_stall_continuation(messages) is True

    def test_stall_with_list_of_parts_content(self):
        """User message content as list-of-parts (OpenAI format) starting
        with the prefix should be detected."""
        messages = [
            {"role": "user", "content": "Run date."},
            {"role": "assistant", "content": "I'll check."},
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": build_action_stall_continuation()},
                ],
            },
        ]
        assert latest_user_message_is_stall_continuation(messages) is True

    def test_stall_with_list_of_string_parts(self):
        """User content as list of plain strings starting with prefix."""
        messages = [
            {"role": "user", "content": "Run date."},
            {"role": "assistant", "content": "I'll check."},
            {
                "role": "user",
                "content": [build_action_stall_continuation()],
            },
        ]
        assert latest_user_message_is_stall_continuation(messages) is True


# ── latest_user_message_is_stall_continuation — False cases ─────────


class TestStallContinuationRejects:
    def test_assistant_with_tool_calls(self):
        """If the assistant DID emit tool_calls, it's not a stall."""
        messages = [
            {"role": "user", "content": "Run date."},
            {
                "role": "assistant",
                "content": "",
                "tool_calls": [
                    {
                        "id": "call_1",
                        "type": "function",
                        "function": {"name": "terminal", "arguments": "{}"},
                    }
                ],
            },
            {"role": "user", "content": build_action_stall_continuation()},
        ]
        assert latest_user_message_is_stall_continuation(messages) is False

    def test_regular_user_message(self):
        """Last user message without the stall prefix → not a stall continuation."""
        messages = [
            {"role": "user", "content": "Inspect the repo."},
            {"role": "assistant", "content": "I'll inspect it."},
            {"role": "user", "content": "continue please"},
        ]
        assert latest_user_message_is_stall_continuation(messages) is False

    def test_empty_messages(self):
        assert latest_user_message_is_stall_continuation([]) is False

    def test_single_message(self):
        """A single user message with the prefix still needs a preceding
        assistant message to qualify as a stall continuation."""
        messages = [
            {"role": "user", "content": build_action_stall_continuation()},
        ]
        assert latest_user_message_is_stall_continuation(messages) is False

    def test_none_content_on_last_message(self):
        """Last message content=None → _message_content_text returns '',
        which doesn't start with the prefix."""
        messages = [
            {"role": "user", "content": "Hi"},
            {"role": "assistant", "content": "I'll check."},
            {"role": "user", "content": None},
        ]
        assert latest_user_message_is_stall_continuation(messages) is False

    def test_none_content_on_assistant_message(self):
        """Assistant with None content and no tool_calls is still a valid
        stall pattern (content=None is not the blocker; missing tool_calls
        is). This should return True, not False — testing here to document
        the behavior."""
        messages = [
            {"role": "user", "content": "Hi"},
            {"role": "assistant", "content": None},
            {"role": "user", "content": build_action_stall_continuation()},
        ]
        assert latest_user_message_is_stall_continuation(messages) is True

    def test_list_of_parts_content_without_prefix(self):
        """List-of-parts content that doesn't start with the prefix → False."""
        messages = [
            {"role": "user", "content": "Hi"},
            {"role": "assistant", "content": "I'll check."},
            {
                "role": "user",
                "content": [{"type": "text", "text": "just a regular message"}],
            },
        ]
        assert latest_user_message_is_stall_continuation(messages) is False

    def test_list_of_parts_content_empty(self):
        """Empty list-of-parts → empty text → doesn't start with prefix."""
        messages = [
            {"role": "user", "content": "Hi"},
            {"role": "assistant", "content": "I'll check."},
            {"role": "user", "content": []},
        ]
        assert latest_user_message_is_stall_continuation(messages) is False

    def test_marker_not_in_last_position(self):
        """User message that STARTS with the prefix but is NOT the last
        message → False. The stall continuation must be the request tail."""
        messages = [
            {"role": "user", "content": "Inspect the repo."},
            {"role": "assistant", "content": "I'll inspect it."},
            {"role": "user", "content": build_action_stall_continuation()},
            {
                "role": "assistant",
                "content": "",
                "tool_calls": [
                    {
                        "id": "call_1",
                        "type": "function",
                        "function": {"name": "terminal", "arguments": "{}"},
                    }
                ],
            },
            {"role": "tool", "tool_call_id": "call_1", "name": "terminal", "content": "ok"},
        ]
        assert latest_user_message_is_stall_continuation(messages) is False

    def test_stall_marker_but_previous_not_assistant(self):
        """Stall marker as last user message, but the message before it is
        NOT an assistant message (e.g. a tool message) → False."""
        messages = [
            {"role": "user", "content": "Run date."},
            {
                "role": "assistant",
                "content": "",
                "tool_calls": [
                    {
                        "id": "call_1",
                        "type": "function",
                        "function": {"name": "terminal", "arguments": "{}"},
                    }
                ],
            },
            {"role": "tool", "tool_call_id": "call_1", "name": "terminal", "content": "ok"},
            {"role": "user", "content": build_action_stall_continuation()},
        ]
        # messages[-2] is the tool message, not assistant → False
        assert latest_user_message_is_stall_continuation(messages) is False

    def test_last_message_not_user_role(self):
        """If the last message is not role=user → False."""
        messages = [
            {"role": "user", "content": "Hi"},
            {"role": "assistant", "content": "I'll check."},
        ]
        assert latest_user_message_is_stall_continuation(messages) is False

    def test_none_messages(self):
        """None as messages argument → False (not a list)."""
        assert latest_user_message_is_stall_continuation(None) is False


# ── Integration: build → detect roundtrip ────────────────────────────


class TestStallContinuationRoundtrip:
    def test_build_then_detect(self):
        """The output of build_action_stall_continuation() should be
        detectable by latest_user_message_is_stall_continuation() when
        placed as the last user message after a no-tool assistant turn."""
        messages = [
            {"role": "user", "content": "Do the thing."},
            {"role": "assistant", "content": "I'll do the thing now."},
            {"role": "user", "content": build_action_stall_continuation()},
        ]
        assert latest_user_message_is_stall_continuation(messages) is True

    def test_build_then_detect_with_dict_content_parts(self):
        """Same roundtrip but with list-of-parts content on the user message."""
        text = build_action_stall_continuation()
        messages = [
            {"role": "user", "content": "Do the thing."},
            {"role": "assistant", "content": "I'll do the thing now."},
            {"role": "user", "content": [{"type": "text", "text": text}]},
        ]
        assert latest_user_message_is_stall_continuation(messages) is True


# ── Conversation loop nudge contract ─────────────────────────────────


class TestConversationLoopNudgeContract:
    """Verify the conversation loop uses build_action_stall_continuation()
    for the nudge message instead of a hardcoded string.

    The conversation loop (conversation_loop.py) detects action stalls and
    injects a corrective continuation user message. PR #34 refactored the
    hardcoded nudge string into build_action_stall_continuation() so the
    marker is shared between the loop (injection) and the transport
    (detection → tool_choice=required). This test verifies that contract.
    """

    def test_conversation_loop_imports_build_action_stall_continuation(self):
        """conversation_loop.py must import build_action_stall_continuation
        from agent.action_stall — not use a hardcoded string."""
        import inspect
        from agent import conversation_loop
        source = inspect.getsource(conversation_loop)
        assert "from agent.action_stall import build_action_stall_continuation" in source

    def test_conversation_loop_uses_build_function_for_nudge(self):
        """The nudge message content must be build_action_stall_continuation()
        — not a hardcoded '[System: Continue now...]' string."""
        import inspect
        from agent import conversation_loop
        source = inspect.getsource(conversation_loop)
        # The old hardcoded nudge string must NOT be present
        assert "[System: Continue now" not in source
        # The new function call must be present
        assert "build_action_stall_continuation()" in source

    def test_nudge_content_matches_build_output(self):
        """The nudge message built by the loop must produce content that
        starts with ACTION_STALL_CONTINUATION_PREFIX — this is what the
        transport's latest_user_message_is_stall_continuation() looks for."""
        nudge_text = build_action_stall_continuation()
        assert nudge_text.startswith(ACTION_STALL_CONTINUATION_PREFIX)
        # Verify it's detectable as a stall continuation in a message list
        messages = [
            {"role": "user", "content": "Do the thing."},
            {"role": "assistant", "content": "I'll do the thing."},
            {"role": "user", "content": nudge_text},
        ]
        assert latest_user_message_is_stall_continuation(messages) is True
