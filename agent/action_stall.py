"""Action-stall detection and corrective continuation for tool-calling models.

When a model narrates intent to call a tool but emits no ``tool_calls`` in its
assistant message (an "action stall"), the conversation loop injects a
corrective continuation message.  This module provides the continuation text
builder and a helper to detect whether the last user message in a history is
such a stall continuation.

Ported from PR #58368.
"""

from __future__ import annotations

from typing import Any

ACTION_STALL_CONTINUATION_PREFIX = (
    "[System corrective continuation: tool execution required]"
)


def build_action_stall_continuation() -> str:
    """Return the corrective continuation message text.

    The prefix :data:`ACTION_STALL_CONTINUATION_PREFIX` is used by
    :func:`latest_user_message_is_stall_continuation` to detect these
    messages, so it must remain stable.
    """
    return (
        ACTION_STALL_CONTINUATION_PREFIX
        + "\nContinue now. Execute the required tool calls and only send your "
        "final answer after completing the task."
    )


def _message_content_text(msg: dict[str, Any]) -> str:
    """Extract a plain-text representation of a message's content.

    Handles both string content and list-of-parts content (OpenAI format).
    """
    content = msg.get("content")
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for part in content:
            if isinstance(part, dict):
                # text part
                text = part.get("text")
                if isinstance(text, str):
                    parts.append(text)
            elif isinstance(part, str):
                parts.append(part)
        return "".join(parts)
    return ""


def latest_user_message_is_stall_continuation(messages: list[dict[str, Any]]) -> bool:
    """Return ``True`` when the last message is an action-stall continuation.

    The pattern we look for (walking from the end):

    1. The **last** message is a ``user`` message whose content starts with
       :data:`ACTION_STALL_CONTINUATION_PREFIX`.
    2. The message **before** that is an ``assistant`` message with **no**
       ``tool_calls`` (the stall — the model narrated intent but didn't call).
    3. There is no tool evidence (no ``tool`` role message) between the
       assistant message and the stall continuation.

    If any condition fails, return ``False``.
    """
    if not messages:
        return False

    last = messages[-1]
    if last.get("role") != "user":
        return False

    last_text = _message_content_text(last)
    if not last_text.startswith(ACTION_STALL_CONTINUATION_PREFIX):
        return False

    # Need at least one message before the stall continuation
    if len(messages) < 2:
        return False

    prev = messages[-2]
    if prev.get("role") != "assistant":
        return False

    # The assistant message must have NO tool_calls — that's the stall
    if prev.get("tool_calls"):
        return False

    # No tool-role messages should appear between prev (assistant) and last
    # (user continuation).  Since we already know last is the immediate
    # successor of prev (they are messages[-2] and messages[-1]), there are
    # no messages between them, so this condition is trivially satisfied.
    return True
