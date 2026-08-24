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


def capture_counterfactuals(pattern_id: str, versions: list[str], size: int) -> None:
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
        done = 0
        for tid in ids:
            trace = store.get_trace(tid)
            world_hash = cap.sha_text("placeholder")
            from apps.api.replay import world as world_mod

            world_hash = world_mod.sha256_file(world_mod.paths.world_path(tid))
            key = cf.capture_key(
                trace, {**cfg, "tools": tools},
                config_hash=cfg_hash, tools_hash=t_hash,
                corpus_hash=corpus_hash, world_hash=world_hash,
            )
            if cap.load_exact(key) is not None:
                done += 1
                continue
            t0 = time.time()
            _, _, payload = cf.run_candidate_live(trace, run_id, {**cfg, "tools": tools})
            cap.save(key, payload, notes=f"Live counterfactual run for {version}.")
            done += 1
            print(f"  ✓ {version} {tid}  ({time.time() - t0:.1f}s)  [{done}/{len(ids)}]")
        print(f"  → {version}: {done} counterfactual runs captured")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("stage", choices=["diagnoses", "proposals", "patch", "counterfactuals", "all"])
    ap.add_argument("--pattern", default=None, help="pattern id for patch/counterfactual stages")
    ap.add_argument("--size", type=int, default=12, help="cohort size per arm")
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
            versions = [
                c.version for c in store.list_configs() if c.version.startswith("v2-candidate")
            ]
        print(f"Capturing counterfactual runs for {versions} on {target}…")
        capture_counterfactuals(target, versions, args.size)

    n = len(list((cap.paths.CAPTURES).glob("*/*.json")))
    print(f"\nDone. {n} capture artifacts under fixtures/captures/")


if __name__ == "__main__":
    main()
