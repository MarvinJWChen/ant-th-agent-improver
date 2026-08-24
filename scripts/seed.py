"""CLI entrypoint for seeding the demo corpus.

Usage:
    uv run python -m scripts.seed --fresh

Without --fresh this is a no-op if var/traces.db already exists.
"""
from __future__ import annotations

import argparse
import shutil
import sys
from typing import Any

from apps.api import paths
from scripts import gen_corpus


def hidden_labels_path():
    # Deliberately not part of apps/api/paths.py -- see SCHEMA.md: only
    # scripts/ may know this path.
    return paths.VAR / "hidden_labels.db"


def _clean() -> None:
    for p in (paths.TRACES_DB, paths.CONFIGS_DB, hidden_labels_path()):
        if p.exists():
            p.unlink()
    if paths.WORLDS_DIR.exists():
        shutil.rmtree(paths.WORLDS_DIR)


def _print_summary(data: dict[str, Any]) -> None:
    traces = data["traces"]
    events = data["events"]
    total_events = sum(len(v) for v in events.values())

    outcome_counts: dict[str, int] = {}
    intent_counts: dict[str, int] = {}
    for t in traces:
        outcome_counts[t["outcome"]] = outcome_counts.get(t["outcome"], 0) + 1
        intent_counts[t["intent"]] = intent_counts.get(t["intent"], 0) + 1

    family_counts: dict[str, int] = {}
    for fam in data["labels"].values():
        family_counts[fam] = family_counts.get(fam, 0) + 1

    print(f"Seeded {len(traces)} traces, {total_events} events, {len(data['worlds'])} world snapshots.")
    print(f"Outcomes:  {outcome_counts}")
    print(f"Intents:   {intent_counts}")
    print(f"Families (offline-only, var/hidden_labels.db): {family_counts}")
    print(f"Config:    v1 seeded (config_hash={data['config']['config_hash'][:12]}...)")


def seed(fresh: bool) -> None:
    paths.ensure_dirs()

    if not fresh and paths.TRACES_DB.exists():
        print("var/traces.db already exists; nothing to do (pass --fresh to regenerate).")
        return

    _clean()
    paths.ensure_dirs()

    data = gen_corpus.generate(seed=gen_corpus.SEED)

    gen_corpus.write_traces_db(paths.TRACES_DB, data["traces"], data["events"])
    gen_corpus.write_worlds(data["worlds"])
    gen_corpus.write_hidden_labels_db(hidden_labels_path(), data["labels"])
    gen_corpus.write_configs_db(paths.CONFIGS_DB, data["config"])

    _print_summary(data)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Seed the demo corpus: var/traces.db, var/worlds/*.sqlite, "
        "var/hidden_labels.db, var/configs.db."
    )
    parser.add_argument("--fresh", action="store_true", help="Delete and regenerate everything.")
    args = parser.parse_args(argv)
    seed(fresh=args.fresh)
    return 0


if __name__ == "__main__":
    sys.exit(main())
