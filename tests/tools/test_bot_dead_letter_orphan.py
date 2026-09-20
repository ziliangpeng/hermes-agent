"""Behavior contracts for orphan_dead_letter_deliveries (dead-letter retirement)."""


def _record_or_raise(profile_home, delivery_id):
    from tools.bot_live_delivery import read_delivery_result

    record = read_delivery_result(profile_home, delivery_id)
    assert record is not None, f"receipt {delivery_id} vanished"
    return record


def _owner_or_raise(profile_home):
    from tools.bot_live_delivery import find_canonical_live_owner

    owner = find_canonical_live_owner(profile_home)
    assert owner is not None, "no capable live owner found"
    return owner


def test_orphan_marks_dead_pinned_envelopes_and_keeps_receipt(tmp_path):
    from tools import bot_live_delivery as mailbox

    owner = dict(profile_home=str(tmp_path.resolve()), session_id="chat",
                 lease_id="dead-lease", live_session_id="dead-live")
    queued = mailbox.deliver_to_live_owner(tmp_path, owner, "lost message",
                                           delivery_id="d" * 32)
    assert queued["status"] == "queued"

    # Live lease set does NOT contain the pinned lease -> envelope is dead.
    orphaned = mailbox.orphan_dead_letter_deliveries(tmp_path, {"some-other-lease"})
    assert len(orphaned) == 1
    assert orphaned[0]["delivery_id"] == "d" * 32
    record = _record_or_raise(tmp_path, "d" * 32)
    assert record["status"] == "orphaned"
    assert record["reason"] == "dead_letter_pinned_lease_gone"
    # The original message survives in the permanent receipt for redelivery/audit.
    assert record["message"] == "lost message"
    assert record["owner"]["lease_id"] == "dead-lease"


def test_orphan_never_touches_live_pinned_or_terminal_envelopes(tmp_path):
    from tools import bot_live_delivery as mailbox

    live_owner = dict(profile_home=str(tmp_path.resolve()), session_id="chat",
                      lease_id="live-lease", live_session_id="live-id")
    mailbox.deliver_to_live_owner(tmp_path, live_owner, "still deliverable",
                                  delivery_id="e" * 32)
    settled_owner = dict(profile_home=str(tmp_path.resolve()), session_id="chat",
                         lease_id="gone-lease", live_session_id="gone-live")
    mailbox.deliver_to_live_owner(tmp_path, settled_owner, "already settled",
                                  delivery_id="f" * 32)
    claim = mailbox.claim_pending_delivery(tmp_path, settled_owner)
    assert claim is not None
    mailbox.complete_delivery(tmp_path, "f" * 32, status="settled", reply="done")

    # The pinned lease is alive -> its queued envelope must be left alone.
    assert mailbox.orphan_dead_letter_deliveries(tmp_path, {"live-lease"}) == []
    assert _record_or_raise(tmp_path, "e" * 32)["status"] == "queued"
    # Terminal envelopes stay terminal.
    assert _record_or_raise(tmp_path, "f" * 32)["status"] == "settled"


def test_orphan_is_idempotent_and_missing_mailbox_is_noop(tmp_path):
    from tools import bot_live_delivery as mailbox

    owner = dict(profile_home=str(tmp_path.resolve()), session_id="chat",
                 lease_id="gone-lease", live_session_id="gone-live")
    mailbox.deliver_to_live_owner(tmp_path, owner, "lost", delivery_id="a" * 32)
    first = mailbox.orphan_dead_letter_deliveries(tmp_path, set())
    assert len(first) == 1
    # Second sweep reports nothing new and does not rewrite the receipt.
    second = mailbox.orphan_dead_letter_deliveries(tmp_path, set())
    assert second == []
    assert _record_or_raise(tmp_path, "a" * 32)["status"] == "orphaned"
    # A profile with no mailbox directory at all is a no-op, not an error.
    empty = tmp_path / "empty-profile"
    empty.mkdir()
    assert mailbox.orphan_dead_letter_deliveries(empty, set()) == []


def test_readmit_requeues_orphaned_message_for_the_current_owner(tmp_path):
    from tools import bot_live_delivery as mailbox

    dead = dict(profile_home=str(tmp_path.resolve()), session_id="chat",
                lease_id="dead-lease", live_session_id="dead-live")
    mailbox.deliver_to_live_owner(tmp_path, dead, "lost message", delivery_id="a" * 32)
    assert mailbox.orphan_dead_letter_deliveries(tmp_path, set()) != []

    # A NEW live owner of the SAME chat session picks it up: the fresh envelope
    # must be claimable by that owner and carry the original text.
    current = dict(profile_home=str(tmp_path.resolve()), session_id="chat",
                   lease_id="live-2", live_session_id="live-2")
    readmitted = mailbox.readmit_orphaned_deliveries(tmp_path, current)
    assert len(readmitted) == 1
    fresh = readmitted[0]
    assert fresh["status"] == "queued"
    assert "lost message" in fresh["message"]
    assert mailbox._REDELIVERY_NOTE.strip() in fresh["message"]
    # The old receipt is terminal with a pointer to the fresh envelope.
    old = _record_or_raise(tmp_path, "a" * 32)
    assert old["status"] == "re-admitted"
    assert old["readmitted_as"] == fresh["delivery_id"]
    # The new owner claims and settles the fresh envelope through the normal path.
    claim = mailbox.claim_pending_delivery(tmp_path, current)
    assert claim is not None and claim["delivery_id"] == fresh["delivery_id"]
    mailbox.complete_delivery(tmp_path, fresh["delivery_id"], status="settled", reply="ack")
    # Re-running the sweeper finds nothing more to do.
    assert mailbox.readmit_orphaned_deliveries(tmp_path, current) == []
    assert mailbox.claim_pending_delivery(tmp_path, current) is None


def test_readmit_refuses_a_different_chats_lineage(tmp_path):
    from hermes_state import SessionDB
    from tools import bot_live_delivery as mailbox

    # Envelope orphaned on chat A must not be re-admitted to live owner of chat B.
    dead = dict(profile_home=str(tmp_path.resolve()), session_id="chat-a",
                lease_id="dead-lease", live_session_id="dead-live")
    mailbox.deliver_to_live_owner(tmp_path, dead, "for chat A only", delivery_id="b" * 32)
    mailbox.orphan_dead_letter_deliveries(tmp_path, set())

    db = SessionDB(db_path=tmp_path / "state.db")
    db.create_session(session_id="chat-b", source="cli")
    db.set_session_title("chat-b", "Bot Chat")
    db.close()
    other = dict(profile_home=str(tmp_path.resolve()), session_id="chat-b",
                 lease_id="live-b", live_session_id="live-b")
    assert mailbox.readmit_orphaned_deliveries(tmp_path, other) == []
    assert _record_or_raise(tmp_path, "b" * 32)["status"] == "orphaned"


def test_repair_dead_letters_end_to_end_with_a_real_registry(tmp_path):
    """The poller-path sweep: a queued envelope pinned to a DEAD lease is re-admitted
    to the current capable owner and delivered through the normal claim path."""
    from hermes_cli.active_sessions import try_acquire_active_session
    from hermes_state import SessionDB
    from tools import bot_live_delivery as mailbox

    # The dying window: a live lease whose envelope is queued against it.
    db = SessionDB(db_path=tmp_path / "state.db")
    db.create_session(session_id="chat", source="cli")
    db.set_session_title("chat", "Bot Chat")
    dying_meta = dict(live_session_id="old-live", bot_live_delivery_consumer=True)
    dying, refusal = try_acquire_active_session(
        session_id="chat", surface="desktop", config={}, registry_home=tmp_path,
        metadata=dying_meta)
    assert refusal is None and dying is not None
    dead_owner = _owner_or_raise(tmp_path)
    mailbox.deliver_to_live_owner(tmp_path, dead_owner, "message from the past",
                                  delivery_id="c" * 32)
    dying.release()  # the window closes; the envelope is now a dead letter

    # A NEW capable window of the same chat opens.
    fresh_meta = dict(live_session_id="new-live", bot_live_delivery_consumer=True)
    fresh_lease, fresh_refusal = try_acquire_active_session(
        session_id="chat", surface="desktop", config={}, registry_home=tmp_path,
        metadata=fresh_meta)
    assert fresh_refusal is None and fresh_lease is not None
    current = _owner_or_raise(tmp_path)
    assert current["lease_id"] == fresh_lease.lease_id
    try:
        # One poller sweep repairs everything: dead letter re-admitted to `current`.
        repaired = mailbox.repair_dead_letters(tmp_path, current)
        assert len(repaired) == 1
        assert "message from the past" in repaired[0]["message"]
        # The fresh envelope flows through the normal claim -> settle path.
        claim = mailbox.claim_pending_delivery(tmp_path, current)
        assert claim is not None
        assert claim["message"] == repaired[0]["message"]
        mailbox.complete_delivery(tmp_path, claim["delivery_id"], status="settled", reply="ok")
        # Nothing left to repair on the next sweep; a no-dead-letter mailbox is a no-op.
        assert mailbox.repair_dead_letters(tmp_path, current) == []
    finally:
        fresh_lease.release()
        db.close()


def test_repair_leaves_a_live_foreign_lease_envelope_alone(tmp_path):
    """A queued envelope pinned to a DIFFERENT but still-live lease (another open
    window of the same chat) must not be orphaned or stolen by the sweep."""
    from hermes_cli.active_sessions import try_acquire_active_session
    from hermes_state import SessionDB
    from tools import bot_live_delivery as mailbox

    db = SessionDB(db_path=tmp_path / "state.db")
    db.create_session(session_id="chat", source="cli")
    db.set_session_title("chat", "Bot Chat")
    sibling_meta = dict(live_session_id="sib-live", bot_live_delivery_consumer=True)
    sibling, refusal = try_acquire_active_session(
        session_id="chat", surface="desktop", config={}, registry_home=tmp_path,
        metadata=sibling_meta)
    assert refusal is None and sibling is not None
    sibling_owner = _owner_or_raise(tmp_path)
    mailbox.deliver_to_live_owner(tmp_path, sibling_owner, "for my sibling window",
                                  delivery_id="e" * 32)
    # The sibling lease stays ALIVE (entry present in the registry).
    try:
        assert mailbox.repair_dead_letters(tmp_path, sibling_owner) == []
        assert _record_or_raise(tmp_path, "e" * 32)["status"] == "queued"
    finally:
        sibling.release()
        db.close()
