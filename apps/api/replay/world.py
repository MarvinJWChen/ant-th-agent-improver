"""Frozen-world isolation.

The whole safety argument rests on one simple mechanic: an arm never touches the
recorded world file. It gets a byte-for-byte copy, and every read and write it
performs happens against that copy. Two arms of the same trace therefore run
against two independent clones of identical starting state, and we can prove it
by publishing both clone hashes plus the unchanged hash of the source.
"""
from __future__ import annotations

import hashlib
import shutil
import sqlite3
from dataclasses import dataclass
from pathlib import Path

from apps.api import paths


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


@dataclass(frozen=True)
class Clone:
    trace_id: str
    arm: str
    path: Path
    sha256: str
    source_path: Path
    source_sha256: str


def clone_world(trace_id: str, run_id: str, arm: str) -> Clone:
    src = paths.world_path(trace_id)
    if not src.exists():
        raise FileNotFoundError(f"no frozen world for {trace_id}")
    src_sha = sha256_file(src)
    dest_dir = paths.RUNS_DIR / run_id / arm
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / f"{trace_id}.sqlite"
    shutil.copyfile(src, dest)
    return Clone(
        trace_id=trace_id,
        arm=arm,
        path=dest,
        sha256=sha256_file(dest),
        source_path=src,
        source_sha256=src_sha,
    )


def source_unchanged(clone: Clone) -> bool:
    """The invariant that makes replay safe to run against production recordings."""
    return sha256_file(clone.source_path) == clone.source_sha256


def open_clone(clone: Clone) -> sqlite3.Connection:
    conn = sqlite3.connect(clone.path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=OFF")
    return conn


def world_meta(conn: sqlite3.Connection) -> dict[str, str]:
    return {r["key"]: r["value"] for r in conn.execute("SELECT key, value FROM world_meta")}
