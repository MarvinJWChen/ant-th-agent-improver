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


def content_hash(path: Path) -> str:
    """Hash the world's *contents*, not its file bytes.

    A byte hash identifies one particular file, which is what we want when
    proving two arms got separate copies. It is the wrong thing for provenance:
    a different SQLite build can lay out identical data differently, so a capture
    made on a laptop would look stale in a container even though the world is the
    same. Hashing the rows keeps provenance portable.
    """
    h = hashlib.sha256()
    with sqlite3.connect(f"file:{path}?mode=ro", uri=True) as conn:
        tables = [
            r[0]
            for r in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
            )
        ]
        for t in tables:
            h.update(f"::{t}::".encode())
            cols = [r[1] for r in conn.execute(f"PRAGMA table_info({t})")]
            order = ", ".join(cols)
            for row in conn.execute(f"SELECT {order} FROM {t} ORDER BY {order}"):
                h.update("|".join("" if v is None else str(v) for v in row).encode())
    return h.hexdigest()


def open_clone(clone: Clone) -> sqlite3.Connection:
    conn = sqlite3.connect(clone.path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=OFF")
    return conn


def world_meta(conn: sqlite3.Connection) -> dict[str, str]:
    return {r["key"]: r["value"] for r in conn.execute("SELECT key, value FROM world_meta")}
