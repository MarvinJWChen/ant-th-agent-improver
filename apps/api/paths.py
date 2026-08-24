"""Single source of truth for on-disk locations.

Note: hidden_labels.db is deliberately NOT exposed here. Runtime code must have
no way to reach the offline validation labels; scripts/ constructs that path
itself. See SCHEMA.md.
"""
from __future__ import annotations

import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
VAR = Path(os.environ.get("AGENT_IMPROVER_VAR", ROOT / "var"))
FIXTURES = ROOT / "fixtures"
CAPTURES = FIXTURES / "captures"

TRACES_DB = VAR / "traces.db"
CONFIGS_DB = VAR / "configs.db"
WORLDS_DIR = VAR / "worlds"
RUNS_DIR = VAR / "runs"
WEB_DIST = ROOT / "apps" / "web" / "dist"


def world_path(trace_id: str) -> Path:
    return WORLDS_DIR / f"{trace_id}.sqlite"


def ensure_dirs() -> None:
    for d in (VAR, WORLDS_DIR, RUNS_DIR, CAPTURES):
        d.mkdir(parents=True, exist_ok=True)
