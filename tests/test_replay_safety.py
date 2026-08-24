"""Replay safety invariants.

These protect the central claim: replaying production traces against recorded
state can never touch anything real, and can never corrupt the recording.
"""
from __future__ import annotations

import pytest

from apps.api import store
from apps.api.detect import pipeline
from apps.api.replay import world as world_mod
from apps.api.replay.baseline import run_baseline
from apps.api.replay.ledger import Ledger, UnknownEffectError
from apps.api.replay.tools import ToolHost

pytestmark = pytest.mark.skipif(not store.corpus_available(), reason="corpus not seeded")


@pytest.fixture(scope="module")
def sample_trace_id() -> str:
    disc = pipeline.discover()
    return disc.patterns[0].exemplar_trace_ids[0]


def test_arms_get_separate_clones_of_identical_state(sample_trace_id):
    a = world_mod.clone_world(sample_trace_id, "test_iso", "baseline")
    b = world_mod.clone_world(sample_trace_id, "test_iso", "candidate")

    assert a.path != b.path, "each arm must get its own file"
    assert a.sha256 == b.sha256, "both clones must start from identical state"
    assert a.sha256 == a.source_sha256, "a clone is a byte copy of the frozen world"


def test_source_world_is_never_mutated(sample_trace_id):
    src = world_mod.paths.world_path(sample_trace_id)
    before = world_mod.sha256_file(src)

    arm, _ = run_baseline(store.get_trace(sample_trace_id), "test_immutable")

    assert world_mod.sha256_file(src) == before, "replay mutated the recorded world"
    assert arm.source_world_sha256 == before
    # The clone, on the other hand, must show the run's effects.
    assert arm.clone_sha256_after != arm.clone_sha256, "the run left no trace on its clone"


def test_external_effects_are_shadowed_never_executed(sample_trace_id):
    arm, _ = run_baseline(store.get_trace(sample_trace_id), "test_shadow")

    external = [r for r in arm.ledger if r.external]
    assert external, "this trace should exercise at least one external effect"
    for row in external:
        assert row.disposition == "SHADOWED", f"{row.tool} was not shadowed"
    assert arm.external_calls_executed == 0


def test_unknown_tool_fails_closed(sample_trace_id):
    clone = world_mod.clone_world(sample_trace_id, "test_unknown", "probe")
    conn = world_mod.open_clone(clone)
    ledger = Ledger("test_unknown", "probe", sample_trace_id)
    host = ToolHost(conn, ledger, world_mod.world_meta(conn))

    with pytest.raises(UnknownEffectError):
        host.call("wire_transfer", {"order_id": "ord_1", "amount_cents": 500_000})

    assert host.aborted, "the run must abort, not continue past an undeclared effect"
    assert ledger.rows[-1].disposition == "BLOCKED_UNKNOWN_EFFECT"
    assert ledger.unsafe_effects == 1
    conn.close()


def test_reads_come_from_the_clone_not_the_source(sample_trace_id):
    """Mutating the clone changes what a read returns — proving reads are clone-backed."""
    clone = world_mod.clone_world(sample_trace_id, "test_reads", "probe")
    conn = world_mod.open_clone(clone)
    ledger = Ledger("test_reads", "probe", sample_trace_id)
    host = ToolHost(conn, ledger, world_mod.world_meta(conn))
    trace = store.get_trace(sample_trace_id)

    before = host.call("order_lookup", {"order_id": trace.order_id})
    conn.execute("UPDATE orders SET status = 'clone-only' WHERE order_id = ?", (trace.order_id,))
    conn.commit()
    after = host.call("order_lookup", {"order_id": trace.order_id})

    assert before["status"] != "clone-only"
    assert after["status"] == "clone-only"
    assert world_mod.sha256_file(clone.source_path) == clone.source_sha256
    conn.close()


def test_no_network_client_exists_in_the_replay_package():
    """'No production connector' should be provable by absence, not by assertion."""
    import pathlib

    pkg = pathlib.Path(__file__).resolve().parents[1] / "apps/api/replay"
    banned = ("import requests", "import httpx", "urllib.request", "socket.socket", "boto3")
    for path in pkg.glob("*.py"):
        src = path.read_text()
        for token in banned:
            assert token not in src, f"{path.name} contains a network client ({token})"
