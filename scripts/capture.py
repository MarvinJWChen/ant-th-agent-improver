"""Produce the default cached artifacts from real inference.

Every capture this writes is the output of the same versioned code path the
live buttons use — same prompt builder, same schema, same model — stamped with
the provenance of the execution that produced it. That is what makes cached
mode a recording rather than a fixture.

Usage (the key never enters the repo):

    ANTHROPIC_API_KEY=$(cat ~/.anthropic_key) uv run python -m scripts.capture all
"""
from __future__ import annotations

import argparse
import os
import sys
import time

from apps.api import services, store
from apps.api.detect import pipeline
from apps.api.llm import capture as cap
from apps.api.replay import counterfactual as cf
from apps.api.replay import engine


def _require_key() -> None:
    if not os.environ.get("ANTHROPIC_API_KEY"):
        sys.exit(
            "ANTHROPIC_API_KEY is not set.\n"
            "Run:  ANTHROPIC_API_KEY=$(cat ~/.anthropic_key) uv run python -m scripts.capture all"
        )


def capture_diagnoses() -> list[str]:
    disc = pipeline.discover()
    kinds = []
    for p in disc.patterns:
        t0 = time.time()
        res = services.diagnose(p.pattern_id, "live")
        kind = res["diagnosis"]["remediation_kind"]
        kinds.append((p.pattern_id, kind))
        print(f"  ✓ diagnose {p.pattern_id} → {kind}  ({time.time() - t0:.1f}s)")
    return kinds


def capture_proposals(kinds) -> None:
    for pid, _ in kinds:
        t0 = time.time()
        res = services.propose(pid, "live")
        print(f"  ✓ propose  {pid} → {res['kind']}  ({time.time() - t0:.1f}s)")


def capture_patch(pattern_id: str) -> list[str]:
    t0 = time.time()
    res = services.patch(pattern_id, "live")
    versions = [c["candidate_version"] for c in res["candidates"] if c["within_edit_boundary"]]
    print(f"  ✓ patch    {pattern_id} → {versions}  ({time.time() - t0:.1f}s)")
    return versions


def capture_counterfactuals(pattern_id: str, versions: list[str], size: int, workers: int = 6) -> None:
    """Each run is an independent agent loop against its own clone, so they
    parallelise cleanly. The work is almost entirely waiting on the API."""
    from concurrent.futures import ThreadPoolExecutor, as_completed

    target, control = engine.build_cohorts(pattern_id, size)
    ids = target + control
    for version in versions:
        cfg = store.get_config(version).model_dump()
        tools = [
            {"name": t["name"], "description": t["description"], "input_schema": t["input_schema"]}
            for t in cfg["tools"]
        ]
        from apps.api.patch.validate import config_hash as ch
        from apps.api.patch.validate import tools_hash as th

        cfg_hash, t_hash = ch(cfg["model"], cfg["system_prompt"], tools), th(tools)
        corpus_hash = store.corpus_hash()
        run_id = f"capture_{version}"
        from apps.api.replay import world as world_mod

        def one(tid: str) -> str:
            trace = store.get_trace(tid)
            world_hash = world_mod.content_hash(world_mod.paths.world_path(tid))
            key = cf.capture_key(
                trace, {**cfg, "tools": tools},
                config_hash=cfg_hash, tools_hash=t_hash,
                corpus_hash=corpus_hash, world_hash=world_hash,
            )
            if cap.load_exact(key) is not None:
                return f"cached {tid}"
            t0 = time.time()
            try:
                _, outcome, payload = cf.run_candidate_live(
                    trace, run_id, {**cfg, "tools": tools}
                )
            except Exception as e:  # noqa: BLE001 - one bad run must not sink the batch
                return f"FAILED {tid}: {type(e).__name__}: {str(e)[:120]}"
            cap.save(key, payload, notes=f"Live counterfactual run for {version}.")
            fails = ",".join(outcome.failure_labels()) or "clean"
            return f"{tid} {fails} ({time.time() - t0:.1f}s)"

        done = 0
        with ThreadPoolExecutor(max_workers=workers) as pool:
            futures = {pool.submit(one, tid): tid for tid in ids}
            for fut in as_completed(futures):
                done += 1
                print(f"  [{done}/{len(ids)}] {fut.result()}", flush=True)
        print(f"  → {version}: {done} counterfactual runs captured", flush=True)


def captured_kinds() -> list[tuple[str, str]]:
    """Read the remediation kind each captured diagnosis settled on."""
    out = []
    for p in pipeline.discover().patterns:
        try:
            res = services.diagnose(p.pattern_id, "captured")
        except Exception:  # noqa: BLE001
            continue
        if res["provenance"].get("verified"):
            out.append((p.pattern_id, res["diagnosis"]["remediation_kind"]))
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("stage", choices=["diagnoses", "proposals", "patch", "counterfactuals", "all"])
    ap.add_argument("--pattern", default=None, help="pattern id for patch/counterfactual stages")
    ap.add_argument("--size", type=int, default=12, help="cohort size per arm")
    ap.add_argument("--workers", type=int, default=6, help="parallel agent runs")
    args = ap.parse_args()
    _require_key()

    if not store.corpus_available():
        sys.exit("No corpus. Run: uv run python -m scripts.seed --fresh")

    disc = pipeline.discover()
    kinds: list[tuple[str, str]] = []

    if args.stage in ("diagnoses", "all"):
        print("Capturing diagnoses…")
        kinds = capture_diagnoses()
    if args.stage in ("proposals", "all"):
        print("Capturing proposals…")
        if not kinds:
            kinds = [(p.pattern_id, "") for p in disc.patterns]
        capture_proposals(kinds)

    if not kinds:
        kinds = captured_kinds()

    target = args.pattern
    if target is None and kinds:
        target = next((pid for pid, k in kinds if k == "config"), disc.patterns[0].pattern_id)
    target = target or disc.patterns[0].pattern_id

    versions: list[str] = []
    if args.stage in ("patch", "all"):
        print(f"Capturing config patch for {target}…")
        versions = capture_patch(target)
    if args.stage in ("counterfactuals", "all"):
        if not versions:
            prefix = f"v2-{target.lower()}-"
            versions = [
                c.version for c in store.list_configs() if c.version.startswith(prefix)
            ]
        if not versions:
            sys.exit(
                f"No candidate configs for {target}. Run the patch stage first:\n"
                f"  uv run python -m scripts.capture patch --pattern {target}"
            )
        print(f"Capturing counterfactual runs for {versions} on {target}…")
        capture_counterfactuals(target, versions, args.size, args.workers)

    n = len(list((cap.paths.CAPTURES).glob("*/*.json")))
    print(f"\nDone. {n} capture artifacts under fixtures/captures/")


if __name__ == "__main__":
    main()
